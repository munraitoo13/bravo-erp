"""Integration tests for Work Orders, Serial Vault, Outbox Relay, WeasyPrint PDF, and Warranties."""

import hashlib
from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.storage import StorageClient, get_storage_client
from src.main import app
from src.modules.catalog.models import CatalogItem
from src.modules.quotes.models import OutboxEvent, OutboxStatus, Quote
from src.modules.tasks.outbox_relay import process_pending_outbox_events
from src.modules.tasks.warranty_cron import scan_expiring_warranties
from src.modules.work_orders.models import WorkOrder
from src.seed.demo_seeder import (
    DEMO_ACTIVE_WORK_ORDER_ID,
    DEMO_IN_PROGRESS_QUOTE_ID,
    DEMO_SENT_QUOTE_ID,
    DEMO_SENT_QUOTE_PUBLIC_TOKEN,
    seed_demo_tenant,
)


class InMemoryStorageClient(StorageClient):
    """In-memory S3/MinIO double for deterministic verification of uploaded PDF and photo bytes."""

    def __init__(self) -> None:
        super().__init__()
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def upload_bytes(
        self,
        *,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Store uploaded bytes and content_type in memory keyed by object_key."""
        self.objects[object_key] = (data, content_type)
        return object_key

    async def generate_presigned_download_url(
        self,
        *,
        object_key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        """Return a deterministic mock presigned URL for testing."""
        return f"http://localhost:9000/bravo-erp/{object_key}?expires={expires_in_seconds}"


async def test_end_to_end_quote_approval_work_order_completion_pdf_and_sha256_verifier(
    async_client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Verify full flow: Quote Approval -> Outbox PDF -> WorkOrder Guards & Serials -> Verify."""
    storage_double = InMemoryStorageClient()
    app.dependency_overrides[get_storage_client] = lambda: storage_double

    async with session_maker() as seed_session:
        await seed_demo_tenant(seed_session, force_reset=True)
        await seed_session.commit()

    # 1. Authenticate as Demo OWNER and Demo TECHNICIAN
    owner_login = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "OWNER"},
    )
    assert owner_login.status_code == 200
    owner_token = owner_login.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    tech_login = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "TECHNICIAN"},
    )
    assert tech_login.status_code == 200
    tech_token = tech_login.json()["access_token"]
    tech_headers = {"Authorization": f"Bearer {tech_token}"}

    # 2. Public Client approves Demo Quote #1 -> creates WorkOrder & emits QuoteApprovedEvent
    approve_resp = await async_client.post(
        f"/api/v1/public/quotes/{DEMO_SENT_QUOTE_PUBLIC_TOKEN}/approve",
        json={"accepted_terms": True, "client_notes": "Liberado na portaria às 08h."},
        headers={"X-Forwarded-For": "177.84.12.99"},
    )
    assert approve_resp.status_code == 200
    approved_body = approve_resp.json()
    assert approved_body["status"] == "APPROVED"
    new_wo_id = approved_body["work_order_id"]
    assert new_wo_id is not None

    # 3. Process pending outbox events -> WeasyPrint generates PDF for Quote #1
    async with session_maker() as relay_session:
        relay_summary = await process_pending_outbox_events(
            relay_session,
            storage_client=storage_double,
        )
        assert relay_summary.processed_count >= 1
        assert relay_summary.failed_count == 0

        q1 = await relay_session.scalar(select(Quote).where(Quote.id == DEMO_SENT_QUOTE_ID))
        assert q1 is not None
        assert q1.pdf_storage_key is not None
        assert q1.pdf_sha256_hash is not None
        assert len(q1.pdf_sha256_hash) == 64

        stored_pdf_bytes, stored_mime = storage_double.objects[q1.pdf_storage_key]
        assert stored_mime == "application/pdf"
        assert stored_pdf_bytes.startswith(b"%PDF-")
        assert hashlib.sha256(stored_pdf_bytes).hexdigest() == q1.pdf_sha256_hash
        q1_approved_hash = q1.pdf_sha256_hash

    # Verify public SHA-256 endpoint confirms Quote #1 authenticity
    verify_q1_resp = await async_client.get(f"/api/v1/verify/{q1_approved_hash}")
    assert verify_q1_resp.status_code == 200
    verify_q1_json = verify_q1_resp.json()
    assert verify_q1_json["verified"] is True
    assert verify_q1_json["quote_id"] == str(DEMO_SENT_QUOTE_ID)
    assert verify_q1_json["quote_status"] == "APPROVED"
    assert verify_q1_json["approved_by_ip"] == "177.84.12.99"

    # 4. Test WorkOrder start and completion guards on newly created WorkOrder (new_wo_id)
    start_resp = await async_client.post(
        f"/api/v1/work-orders/{new_wo_id}/start",
        headers=tech_headers,
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "IN_FIELD"
    assert start_resp.json()["quote_status"] == "IN_PROGRESS"

    # Guard 1 failure: Unchecked checklist steps
    fail_chk_resp = await async_client.post(
        f"/api/v1/work-orders/{new_wo_id}/complete",
        headers=tech_headers,
    )
    assert fail_chk_resp.status_code == 422
    assert fail_chk_resp.json()["errors"][0]["reason"] == "unchecked_checklist_step"

    # Check all 5 checklist steps on new_wo_id
    chk_all_resp = await async_client.patch(
        f"/api/v1/work-orders/{new_wo_id}/checklist",
        headers=tech_headers,
        json={
            "steps": [{"step_id": f"step_{i}", "is_checked": True} for i in range(1, 6)],
            "cloud_p2p_id": "ITB-P2P-NEWWO01",
        },
    )
    assert chk_all_resp.status_code == 200

    # Guard 2 failure: Missing installation photos on new_wo_id
    fail_photo_resp = await async_client.post(
        f"/api/v1/work-orders/{new_wo_id}/complete",
        headers=tech_headers,
    )
    assert fail_photo_resp.status_code == 422
    assert fail_photo_resp.json()["errors"][0]["reason"] == "missing_installation_photos"

    # Upload an installation photo via multipart/form-data to new_wo_id
    upload_photo_resp = await async_client.post(
        f"/api/v1/work-orders/{new_wo_id}/photos",
        headers=tech_headers,
        files={"file": ("rack_portaria.jpg", b"\xff\xd8\xff\xe0JFIF_TEST_JPEG", "image/jpeg")},
    )
    assert upload_photo_resp.status_code == 201
    assert len(upload_photo_resp.json()["installation_photos_keys"]) == 1

    # Guard 3 failure: Missing hardware serial numbers on new_wo_id
    fail_sn_resp = await async_client.post(
        f"/api/v1/work-orders/{new_wo_id}/complete",
        headers=tech_headers,
    )
    assert fail_sn_resp.status_code == 422
    assert fail_sn_resp.json()["errors"][0]["reason"] == "missing_serial_numbers"

    # 5. Now complete Demo Work Order #2 (DEMO_ACTIVE_WORK_ORDER_ID) which has 5/6 serials
    wo2_get_resp = await async_client.get(
        f"/api/v1/work-orders/{DEMO_ACTIVE_WORK_ORDER_ID}",
        headers=tech_headers,
    )
    assert wo2_get_resp.status_code == 200
    wo2_data = wo2_get_resp.json()
    assert wo2_data["status"] == "IN_FIELD"

    # Find the VHL-1120-B camera catalog_item_id that needs 1 more serial number (3 of 4 registered)
    vhl_summary = next(s for s in wo2_data["required_serials_summary"] if s["sku"] == "VHL-1120-B")
    assert vhl_summary["required_quantity"] == 4
    assert vhl_summary["registered_quantity"] == 3
    assert vhl_summary["is_satisfied"] is False
    vhl_catalog_item_id = vhl_summary["catalog_item_id"]

    # Check the remaining 2 checklist steps (step_4 and step_5) on DEMO_ACTIVE_WORK_ORDER_ID
    wo2_chk_resp = await async_client.patch(
        f"/api/v1/work-orders/{DEMO_ACTIVE_WORK_ORDER_ID}/checklist",
        headers=tech_headers,
        json={
            "steps": [
                {"step_id": "step_4", "is_checked": True},
                {"step_id": "step_5", "is_checked": True},
            ],
        },
    )
    assert wo2_chk_resp.status_code == 200

    # Register the 4th VHL-1120-B camera serial number
    reg_sn_resp = await async_client.post(
        f"/api/v1/work-orders/{DEMO_ACTIVE_WORK_ORDER_ID}/serials",
        headers=tech_headers,
        json={
            "catalog_item_id": vhl_catalog_item_id,
            "serial_number": "ITB-VHL1120-004914",
            "channel_or_slot_label": "BNC-04 (Estacionamento)",
        },
    )
    assert reg_sn_resp.status_code == 201
    reg_sn_data = reg_sn_resp.json()
    assert reg_sn_data["serial_number"] == "ITB-VHL1120-004914"
    expected_warranty = (datetime.now(UTC).date() + timedelta(days=365)).isoformat()
    assert reg_sn_data["client_warranty_until"] == expected_warranty
    assert reg_sn_data["distributor_warranty_until"] == expected_warranty

    # Verify duplicate serial number registration is rejected with 422
    dup_sn_resp = await async_client.post(
        f"/api/v1/work-orders/{DEMO_ACTIVE_WORK_ORDER_ID}/serials",
        headers=tech_headers,
        json={
            "catalog_item_id": vhl_catalog_item_id,
            "serial_number": "ITB-VHL1120-004914",
            "channel_or_slot_label": "BNC-04-DUPLICATE",
        },
    )
    assert dup_sn_resp.status_code == 422
    assert dup_sn_resp.json()["errors"][0]["reason"] == "duplicate_serial_number"

    # Complete DEMO_ACTIVE_WORK_ORDER_ID -> deducts stock, sets 12m warranty, emits Outbox
    complete_wo2_resp = await async_client.post(
        f"/api/v1/work-orders/{DEMO_ACTIVE_WORK_ORDER_ID}/complete",
        headers=tech_headers,
        json={"notes": "Obra entregue e testada com o gerente."},
    )
    assert complete_wo2_resp.status_code == 200
    completed_wo2 = complete_wo2_resp.json()
    assert completed_wo2["status"] == "COMPLETED"
    assert completed_wo2["quote_status"] == "COMPLETED"
    assert completed_wo2["warranty_expires_at"] == expected_warranty
    assert len(completed_wo2["installed_serials"]) == 6

    # Verify physical stock and reserved stock were deducted for MHDX-1104 (was stock=10, res=1)
    async with session_maker() as verify_stock_session:
        mhdx_1104 = await verify_stock_session.scalar(
            select(CatalogItem).where(CatalogItem.sku == "MHDX-1104")
        )
        assert mhdx_1104 is not None
        assert mhdx_1104.stock_quantity == 9
        assert mhdx_1104.reserved_quantity == 0

    # 6. Run Outbox Relay to process WorkOrderCompletedEvent -> generates Warranty PDF for Quote #2
    async with session_maker() as relay_session_2:
        relay_summary_2 = await process_pending_outbox_events(
            relay_session_2,
            storage_client=storage_double,
        )
        assert relay_summary_2.processed_count == 1
        assert relay_summary_2.failed_count == 0

        q2 = await relay_session_2.scalar(
            select(Quote).where(Quote.id == DEMO_IN_PROGRESS_QUOTE_ID)
        )
        assert q2 is not None
        assert q2.pdf_storage_key is not None
        assert q2.pdf_sha256_hash is not None
        q2_completed_hash = q2.pdf_sha256_hash

        q2_pdf_bytes, _ = storage_double.objects[q2.pdf_storage_key]
        assert q2_pdf_bytes.startswith(b"%PDF-")
        assert hashlib.sha256(q2_pdf_bytes).hexdigest() == q2_completed_hash

    # 7. Public verification of Quote #2's completed Warranty Certificate SHA-256
    verify_q2_resp = await async_client.get(f"/api/v1/verify/{q2_completed_hash}")
    assert verify_q2_resp.status_code == 200
    verify_q2_data = verify_q2_resp.json()
    assert verify_q2_data["verified"] is True
    assert verify_q2_data["quote_status"] == "COMPLETED"
    assert verify_q2_data["work_order_status"] == "COMPLETED"
    assert verify_q2_data["is_warranty_active"] is True
    assert verify_q2_data["cloud_p2p_id"] == "ITB-P2P-994821BR"
    assert len(verify_q2_data["installed_serials"]) == 6
    verified_sns = {s["serial_number"] for s in verify_q2_data["installed_serials"]}
    assert "ITB-VHL1120-004914" in verified_sns
    assert "WCC6Y7P94821" in verified_sns

    # Unknown SHA-256 returns 404 Problem+JSON
    unknown_hash = "0" * 64
    not_found_resp = await async_client.get(f"/api/v1/verify/{unknown_hash}")
    assert not_found_resp.status_code == 404
    assert not_found_resp.headers["content-type"].startswith("application/problem+json")

    # 8. Test 11-Month Warranty Cron Scanner & GET /api/v1/warranties/expiring
    async with session_maker() as cron_session:
        wo2_db = await cron_session.scalar(
            select(WorkOrder).where(WorkOrder.id == DEMO_ACTIVE_WORK_ORDER_ID)
        )
        assert wo2_db is not None
        # Simulate that WO #2 is now 20 days away from its 12-month warranty expiration
        wo2_db.warranty_expires_at = date.today() + timedelta(days=20)
        wo2_db.preventive_maintenance_alert_sent = False
        await cron_session.commit()

        cron_summary = await scan_expiring_warranties(cron_session)
        assert cron_summary.flagged_count == 1
        assert DEMO_ACTIVE_WORK_ORDER_ID in cron_summary.flagged_work_order_ids

        # Process the emitted WarrantyExpiringAlertEvent in outbox_events
        alert_relay = await process_pending_outbox_events(
            cron_session,
            storage_client=storage_double,
        )
        assert alert_relay.processed_count == 1

        # Verify all outbox events are now PROCESSED
        pending_events = (
            await cron_session.scalars(
                select(OutboxEvent).where(OutboxEvent.status != OutboxStatus.PROCESSED)
            )
        ).all()
        assert len(pending_events) == 0

    expiring_resp = await async_client.get(
        "/api/v1/warranties/expiring",
        headers=owner_headers,
    )
    assert expiring_resp.status_code == 200
    expiring_list = expiring_resp.json()
    assert len(expiring_list) >= 2
    expiring_wo_ids = {item["work_order_id"] for item in expiring_list}
    assert str(DEMO_ACTIVE_WORK_ORDER_ID) in expiring_wo_ids
