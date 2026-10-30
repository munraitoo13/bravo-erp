"""Integration tests for Security Edge Cases, S3 Key Traversal, and Cancellation."""

from datetime import UTC, datetime
from uuid import UUID

from botocore.exceptions import ClientError
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.storage import StorageClient, get_storage_client
from src.main import app
from src.modules.quotes.models import OutboxEvent, OutboxStatus
from src.modules.tasks.outbox_relay import process_pending_outbox_events
from src.seed.demo_seeder import (
    DEMO_ACTIVE_WORK_ORDER_ID,
    DEMO_IN_PROGRESS_QUOTE_ID,
    DEMO_SENT_QUOTE_ID,
    seed_demo_tenant,
)
from tests.integration.test_outbox_and_pdf import InMemoryStorageClient

_SAMPLE_B64_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FailingStorageClient(StorageClient):
    """Storage client double configured to simulate S3 exceptions during PDF generation."""

    def __init__(self, should_fail: bool = True) -> None:
        super().__init__()
        self.should_fail = should_fail
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def upload_bytes(
        self,
        *,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Simulate an S3 ClientError or BotoCoreError on upload."""
        if self.should_fail:
            raise ClientError(
                error_response={
                    "Error": {
                        "Code": "SlowDown",
                        "Message": "503 Service Unavailable",
                    }
                },
                operation_name="PutObject",
            )
        self.objects[object_key] = (data, content_type)
        return object_key

    async def generate_presigned_download_url(
        self,
        *,
        object_key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        return f"http://localhost:9000/bravo-erp/{object_key}?expires={expires_in_seconds}"


async def test_s3_photo_upload_security_guards_and_path_traversal(
    async_client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Verify that photo upload strictly validates MIME type, size limit, and path traversal."""
    storage_double = InMemoryStorageClient()
    app.dependency_overrides[get_storage_client] = lambda: storage_double

    async with session_maker() as seed_session:
        await seed_demo_tenant(seed_session, force_reset=True)
        await seed_session.commit()

    tech_login = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "TECHNICIAN"},
    )
    assert tech_login.status_code == 200
    tech_headers = {"Authorization": f"Bearer {tech_login.json()['access_token']}"}

    # 1. Reject non-whitelisted MIME type (application/x-executable or text/plain)
    invalid_mime_resp = await async_client.post(
        f"/api/v1/work-orders/{DEMO_ACTIVE_WORK_ORDER_ID}/photos",
        headers=tech_headers,
        files={"file": ("malicious.sh", b"#!/bin/bash\necho pwned", "text/plain")},
    )
    assert invalid_mime_resp.status_code == 422
    assert invalid_mime_resp.json()["errors"][0]["reason"] == "unsupported_media_type"

    # 2. Reject file exceeding 10 MB (10 * 1024 * 1024 + 1 bytes)
    too_large_bytes = b"X" * (10 * 1024 * 1024 + 1)
    large_file_resp = await async_client.post(
        f"/api/v1/work-orders/{DEMO_ACTIVE_WORK_ORDER_ID}/photos",
        headers=tech_headers,
        files={"file": ("huge_photo.jpg", too_large_bytes, "image/jpeg")},
    )
    assert large_file_resp.status_code == 422
    assert large_file_resp.json()["errors"][0]["reason"] == "photo_size_limit_exceeded"

    # 3. Reject explicit photo_key containing path traversal '..' via JSON body to /photos
    traversal_resp = await async_client.post(
        f"/api/v1/work-orders/{DEMO_ACTIVE_WORK_ORDER_ID}/photos",
        headers=tech_headers,
        json={
            "photo_key": f"photos/../../other-org/{DEMO_ACTIVE_WORK_ORDER_ID}/stolen.jpg",
            "content_base64": _SAMPLE_B64_PNG,
            "content_type": "image/png",
        },
    )
    assert traversal_resp.status_code == 422
    assert traversal_resp.json()["errors"][0]["reason"] == "invalid_tenant_photo_prefix"

    # 4. Reject explicit photo_key outside the current organization/work_order prefix
    foreign_prefix_resp = await async_client.post(
        f"/api/v1/work-orders/{DEMO_ACTIVE_WORK_ORDER_ID}/photos",
        headers=tech_headers,
        json={
            "photo_key": "photos/00000000-0000-0000-0000-000000000000/arbitrary/photo.jpg",
            "content_base64": _SAMPLE_B64_PNG,
            "content_type": "image/png",
        },
    )
    assert foreign_prefix_resp.status_code == 422
    assert foreign_prefix_resp.json()["errors"][0]["reason"] == "invalid_tenant_photo_prefix"


async def test_cross_entity_quote_cancellation_cascade_and_guards(
    async_client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Verify that quote cancellation cascades to child WorkOrder and respects execution states."""
    storage_double = InMemoryStorageClient()
    app.dependency_overrides[get_storage_client] = lambda: storage_double

    async with session_maker() as seed_session:
        await seed_demo_tenant(seed_session, force_reset=True)
        await seed_session.commit()

    owner_login = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "OWNER"},
    )
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}

    tech_login = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "TECHNICIAN"},
    )
    tech_headers = {"Authorization": f"Bearer {tech_login.json()['access_token']}"}

    # 1. Attempt to cancel Quote #2 (which is IN_PROGRESS with Work Order #2 in IN_FIELD)
    # This is rejected by the Quote state machine (IN_PROGRESS cannot transition to CANCELED)
    reject_cancel = await async_client.post(
        f"/api/v1/quotes/{DEMO_IN_PROGRESS_QUOTE_ID}/cancel",
        headers=owner_headers,
    )
    assert reject_cancel.status_code == 422
    assert "Cannot transition Quote" in reject_cancel.json()["detail"]

    # 2. Create and approve a new Quote with a child WorkOrder in PENDING status
    cust_resp = await async_client.post(
        "/api/v1/customers",
        headers=owner_headers,
        json={
            "name": "Condomínio Cascade Teste",
            "document_cpf_cnpj": "55.444.333/0001-22",
            "phone_whatsapp": "(11) 98888-7777",
            "email": "cascade@condominio.com.br",
            "address_json": {"city": "São Paulo", "state": "SP"},
        },
    )
    assert cust_resp.status_code == 201
    cust_id = cust_resp.json()["id"]

    # Fetch catalog items to create quote
    cat_resp = await async_client.get("/api/v1/catalog", headers=owner_headers)
    assert cat_resp.status_code == 200
    mhdx_item = next(it for it in cat_resp.json() if it["sku"] == "MHDX-1108")

    quote_create = await async_client.post(
        "/api/v1/quotes",
        headers=owner_headers,
        json={
            "customer_id": cust_id,
            "items": [
                {
                    "catalog_item_id": mhdx_item["id"],
                    "quantity": 1,
                    "unit_sale_cents": mhdx_item["sale_price_cents"],
                }
            ],
        },
    )
    assert quote_create.status_code == 201
    new_quote_id = quote_create.json()["id"]

    # Send quote
    send_resp = await async_client.post(
        f"/api/v1/quotes/{new_quote_id}/send",
        headers=owner_headers,
    )
    assert send_resp.status_code == 200

    # Approve quote as Owner -> creates child WorkOrder in PENDING
    approve_resp = await async_client.post(
        f"/api/v1/quotes/{new_quote_id}/approve",
        headers=owner_headers,
    )
    assert approve_resp.status_code == 200
    child_wo_id = approve_resp.json()["work_order_id"]
    assert child_wo_id is not None

    # Verify child WorkOrder is PENDING
    wo_check = await async_client.get(
        f"/api/v1/work-orders/{child_wo_id}",
        headers=tech_headers,
    )
    assert wo_check.status_code == 200
    assert wo_check.json()["status"] == "PENDING"

    # Now OWNER cancels the APPROVED quote -> cascades cancellation to child WorkOrder!
    cancel_resp = await async_client.post(
        f"/api/v1/quotes/{new_quote_id}/cancel",
        headers=owner_headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELED"

    # Verify child WorkOrder was cascaded to CANCELED
    wo_after_cancel = await async_client.get(
        f"/api/v1/work-orders/{child_wo_id}",
        headers=tech_headers,
    )
    assert wo_after_cancel.status_code == 200
    assert wo_after_cancel.json()["status"] == "CANCELED"

    # 3. Verify that technician cannot start or modify a CANCELED WorkOrder
    start_canceled = await async_client.post(
        f"/api/v1/work-orders/{child_wo_id}/start",
        headers=tech_headers,
    )
    assert start_canceled.status_code == 422
    assert start_canceled.json()["errors"][0]["reason"] == "work_order_canceled"


async def test_outbox_relay_s3_exception_handling_and_retry_backoff(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Verify outbox relay catches S3 error, increments retry_count, and isolates transactions."""
    failing_storage = FailingStorageClient(should_fail=True)

    async with session_maker() as session:
        await seed_demo_tenant(session, force_reset=True)
        await session.commit()

        # Insert a pending QuoteSentEvent into outbox_events
        evt = OutboxEvent(
            organization_id=UUID("0192d4a0-0000-7000-8000-000000000001"),
            event_type="QuoteSentEvent",
            status=OutboxStatus.PENDING,
            payload={
                "quote_id": str(DEMO_SENT_QUOTE_ID),
                "organization_id": "0192d4a0-0000-7000-8000-000000000001",
                "public_token": "0192d4a0-7c10-7000-8000-000000000001",
                "correlation_id": "req_test_s3_resilience",
            },
        )
        session.add(evt)
        await session.commit()
        evt_id = evt.id

    # Execute outbox relay with FailingStorageClient
    async with session_maker() as relay_session:
        summary = await process_pending_outbox_events(
            relay_session,
            storage_client=failing_storage,
        )
        assert summary.failed_count >= 1

    # Verify event state in database: still PENDING, retry incremented, next_retry_at scheduled
    async with session_maker() as verify_session:
        reloaded_evt = await verify_session.scalar(
            select(OutboxEvent).where(OutboxEvent.id == evt_id)
        )
        assert reloaded_evt is not None
        assert reloaded_evt.status == OutboxStatus.PENDING
        assert reloaded_evt.retry_count == 1
        assert reloaded_evt.next_retry_at is not None
        assert reloaded_evt.next_retry_at > datetime.now(UTC)
