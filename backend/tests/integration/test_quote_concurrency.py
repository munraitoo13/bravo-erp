"""Integration tests for concurrent Quote approvals (SELECT ... FOR UPDATE), Outbox, and RBAC."""

import asyncio
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.security import UserRole, hash_password
from src.modules.catalog.models import CatalogCategory, CatalogItem
from src.modules.quotes.models import AuditLog, OutboxEvent, OutboxStatus, Quote, QuoteStatus
from src.modules.tenants.models import Organization, User
from src.modules.work_orders.models import WorkOrder, WorkOrderStatus


async def _seed_concurrency_tenant(
    session: AsyncSession,
) -> tuple[Organization, User, User, CatalogItem, CatalogItem, CatalogItem]:
    """Create a tenant with OWNER, TECHNICIAN, and 1 unit of MHDX-1108 DVR in stock."""
    org = Organization(
        name="Bravo Concorrência CFTV Ltda",
        slug="bravo-concorrencia-cftv",
        document_cnpj="31.415.926/0001-53",
        is_demo=False,
    )
    session.add(org)
    await session.flush()

    owner = User(
        organization_id=org.id,
        email="owner@concorrencia.com.br",
        password_hash=hash_password("ConcurrencyPass!1"),
        full_name="Proprietário Concorrência",
        role=UserRole.OWNER,
        is_active=True,
    )
    tech = User(
        organization_id=org.id,
        email="tech@concorrencia.com.br",
        password_hash=hash_password("ConcurrencyPass!1"),
        full_name="Técnico Concorrência",
        role=UserRole.TECHNICIAN,
        is_active=True,
    )
    session.add_all([owner, tech])

    # Only 1 unit of MHDX-1108 available in physical inventory!
    dvr_mhdx = CatalogItem(
        organization_id=org.id,
        sku="MHDX-1108",
        name_pt_br="DVR Intelbras Multi-HD MHDX 1108 8 Canais",
        category=CatalogCategory.DVR,
        brand="Intelbras",
        cost_price_cents=59000,
        sale_price_cents=89900,
        stock_quantity=1,
        reserved_quantity=0,
        specs={
            "native_bnc_channels": 8,
            "extra_ip_channels": 2,
            "supports_bnc_to_ip_conversion": True,
            "max_sata_slots": 1,
            "max_tb_per_slot": 16,
            "max_incoming_bandwidth_mbps": 48,
            "supported_codecs": ["H.264", "H.265", "H.265+"],
            "is_pure_nvr": False,
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
        is_seed_protected=False,
        is_active=True,
    )
    hdd_purple = CatalogItem(
        organization_id=org.id,
        sku="WD20PURZ",
        name_pt_br="HD WD Purple 2TB SATA Vigilância 24x7",
        category=CatalogCategory.HDD,
        brand="Western Digital",
        cost_price_cents=39500,
        sale_price_cents=59900,
        stock_quantity=5,
        reserved_quantity=0,
        specs={
            "capacity_tb": 2,
            "usable_capacity_gb": 1862,
            "surveillance_grade": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 36,
        },
        is_seed_protected=False,
        is_active=True,
    )
    labor_item = CatalogItem(
        organization_id=org.id,
        sku="SRV-INST-PONTO",
        name_pt_br="Mão de Obra de Instalação por Ponto",
        category=CatalogCategory.SERVICE_LABOR,
        brand="Bravo Engenharia",
        cost_price_cents=6000,
        sale_price_cents=14000,
        stock_quantity=9999,
        reserved_quantity=0,
        specs={
            "sub_type": "LABOR_POINT_INSTALL",
            "units_per_package": 1,
            "requires_serial_number": False,
        },
        is_seed_protected=False,
        is_active=True,
    )
    session.add_all([dvr_mhdx, hdd_purple, labor_item])
    await session.commit()
    return org, owner, tech, dvr_mhdx, hdd_purple, labor_item


async def test_parallel_quote_approvals_for_last_stock_unit_enforces_pessimistic_lock(
    async_client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Prove two concurrent approvals for the last MHDX-1108 yield 200 OK and 409 Conflict."""
    async with session_maker() as setup_session:
        org, _, _, dvr_mhdx, hdd_purple, labor_item = await _seed_concurrency_tenant(setup_session)

    # Authenticate as OWNER
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "owner@concorrencia.com.br", "password": "ConcurrencyPass!1"},
    )
    assert login_resp.status_code == 200
    owner_token: str = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {owner_token}"}

    # Create two customers
    cust_a_resp = await async_client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Condomínio Solar do Atlântico",
            "document_cpf_cnpj": "12.345.678/0001-90",
            "phone_whatsapp": "+5511991112222",
            "email": "sindico@solardoatlantico.com.br",
            "address_json": {"city": "Santos", "state": "SP"},
        },
    )
    assert cust_a_resp.status_code == 201
    cust_a_id: str = cust_a_resp.json()["id"]

    cust_b_resp = await async_client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Edifício Empresarial Paulista",
            "document_cpf_cnpj": "98.765.432/0001-10",
            "phone_whatsapp": "+5511993334444",
            "email": "adm@empresarialpaulista.com.br",
            "address_json": {"city": "São Paulo", "state": "SP"},
        },
    )
    assert cust_b_resp.status_code == 201
    cust_b_id: str = cust_b_resp.json()["id"]

    # Create Quote A (orders DVR then HDD) and Quote B (orders HDD then DVR to test UUID sort)
    quote_a_resp = await async_client.post(
        "/api/v1/quotes",
        headers=headers,
        json={
            "customer_id": cust_a_id,
            "valid_days": 15,
            "items": [
                {"catalog_item_id": str(dvr_mhdx.id), "quantity": 1, "is_auto_derived": True},
                {"catalog_item_id": str(hdd_purple.id), "quantity": 1, "is_auto_derived": True},
                {"catalog_item_id": str(labor_item.id), "quantity": 4, "is_auto_derived": True},
            ],
        },
    )
    assert quote_a_resp.status_code == 201
    quote_a_id: str = quote_a_resp.json()["id"]
    token_a: str = quote_a_resp.json()["public_token"]

    quote_b_resp = await async_client.post(
        "/api/v1/quotes",
        headers=headers,
        json={
            "customer_id": cust_b_id,
            "valid_days": 15,
            "items": [
                {"catalog_item_id": str(hdd_purple.id), "quantity": 1, "is_auto_derived": True},
                {"catalog_item_id": str(dvr_mhdx.id), "quantity": 1, "is_auto_derived": True},
                {"catalog_item_id": str(labor_item.id), "quantity": 4, "is_auto_derived": True},
            ],
        },
    )
    assert quote_b_resp.status_code == 201
    quote_b_id: str = quote_b_resp.json()["id"]
    token_b: str = quote_b_resp.json()["public_token"]

    # Transition both quotes DRAFT -> SENT
    send_a = await async_client.post(f"/api/v1/quotes/{quote_a_id}/send", headers=headers)
    send_b = await async_client.post(f"/api/v1/quotes/{quote_b_id}/send", headers=headers)
    assert send_a.status_code == 200
    assert send_b.status_code == 200
    assert send_a.json()["status"] == "SENT"
    assert send_b.json()["status"] == "SENT"

    # Fire both public approvals concurrently via asyncio.gather
    resp_a, resp_b = await asyncio.gather(
        async_client.post(
            f"/api/v1/public/quotes/{token_a}/approve",
            headers={"X-Forwarded-For": "177.54.120.11"},
        ),
        async_client.post(
            f"/api/v1/public/quotes/{token_b}/approve",
            headers={"X-Forwarded-For": "177.54.120.22"},
        ),
    )

    status_codes = sorted([resp_a.status_code, resp_b.status_code])
    assert status_codes == [200, 409]

    winner_resp = resp_a if resp_a.status_code == 200 else resp_b
    loser_resp = resp_b if resp_a.status_code == 200 else resp_a

    # Verify Winner response (200 OK, APPROVED, zero cost/margin leak)
    winner_data = winner_resp.json()
    assert winner_data["status"] == "APPROVED"
    assert winner_data["work_order_id"] is not None
    assert winner_data["version"] == 2
    assert "cost" not in winner_resp.text
    assert "margin" not in winner_resp.text

    # Verify Loser response (409 Conflict RFC 7807 Problem Details)
    assert loser_resp.headers["content-type"].startswith("application/problem+json")
    problem = loser_resp.json()
    assert problem["type"] == "https://bravo-erp.dev/errors/insufficient-stock"
    assert problem["status"] == 409
    assert "MHDX-1108" in problem["detail"]
    assert len(problem["errors"]) == 1
    assert problem["errors"][0]["sku"] == "MHDX-1108"
    assert problem["errors"][0]["available_quantity"] == 0
    assert problem["errors"][0]["requested_quantity"] == 1

    # Inspect database state in an isolated session
    async with session_maker() as verify_session:
        db_dvr = await verify_session.get(CatalogItem, dvr_mhdx.id)
        db_hdd = await verify_session.get(CatalogItem, hdd_purple.id)
        db_labor = await verify_session.get(CatalogItem, labor_item.id)
        assert db_dvr is not None
        assert db_hdd is not None
        assert db_labor is not None

        # Exactly 1 DVR and 1 HDD reserved; SERVICE_LABOR is not physically reserved
        assert db_dvr.stock_quantity == 1
        assert db_dvr.reserved_quantity == 1
        assert db_hdd.stock_quantity == 5
        assert db_hdd.reserved_quantity == 1
        assert db_labor.reserved_quantity == 0

        # Verify WorkOrder created atomically with 5 PT-BR checklist items
        work_orders = (
            await verify_session.scalars(
                select(WorkOrder).where(WorkOrder.organization_id == org.id)
            )
        ).all()
        assert len(work_orders) == 1
        wo = work_orders[0]
        assert str(wo.id) == winner_data["work_order_id"]
        assert wo.status == WorkOrderStatus.PENDING
        assert len(wo.checklist_json) == 5
        assert all(step["is_checked"] is False for step in wo.checklist_json)

        # Verify Transactional Outbox contains 2 QuoteSentEvents + 1 QuoteApprovedEvent
        outbox_events = (
            await verify_session.scalars(
                select(OutboxEvent).where(OutboxEvent.organization_id == org.id)
            )
        ).all()
        sent_events = [e for e in outbox_events if e.event_type == "QuoteSentEvent"]
        approved_events = [e for e in outbox_events if e.event_type == "QuoteApprovedEvent"]
        assert len(sent_events) == 2
        assert len(approved_events) == 1
        assert approved_events[0].status == OutboxStatus.PENDING
        assert approved_events[0].payload["quote_id"] == winner_data["id"]
        assert approved_events[0].payload["work_order_id"] == str(wo.id)
        assert "correlation_id" in approved_events[0].payload

        # Verify AuditLog recorded the approval transition
        winner_quote_uuid = UUID(winner_data["id"])
        audit_logs = (
            await verify_session.scalars(
                select(AuditLog).where(
                    AuditLog.organization_id == org.id,
                    AuditLog.entity_id == winner_quote_uuid,
                )
            )
        ).all()
        assert len(audit_logs) == 3  # QUOTE_CREATED, DRAFT->SENT, SENT->APPROVED
        approval_audit = next(
            log for log in audit_logs if log.new_state.get("status") == QuoteStatus.APPROVED.value
        )
        assert approval_audit.previous_state == {"status": "SENT", "version": 1}
        assert approval_audit.new_state["work_order_id"] == str(wo.id)


async def test_quote_rbac_segregation_and_cancellation_releases_reserved_inventory(
    async_client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Verify Owner vs Technician vs Public quote responses and stock release on cancellation."""
    async with session_maker() as setup_session:
        _, _, _, dvr_mhdx, hdd_purple, _ = await _seed_concurrency_tenant(setup_session)

    owner_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "owner@concorrencia.com.br", "password": "ConcurrencyPass!1"},
    )
    owner_token: str = owner_login.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    tech_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "tech@concorrencia.com.br", "password": "ConcurrencyPass!1"},
    )
    tech_token: str = tech_login.json()["access_token"]
    tech_headers = {"Authorization": f"Bearer {tech_token}"}

    # Create a customer and a quote
    cust_resp = await async_client.post(
        "/api/v1/customers",
        headers=owner_headers,
        json={
            "name": "Clínica Vida Plena Ltda",
            "document_cpf_cnpj": "55.444.333/0001-22",
            "phone_whatsapp": "+5511988887777",
            "email": "contato@vidaplena.com.br",
        },
    )
    customer_id: str = cust_resp.json()["id"]

    # Both OWNER and TECHNICIAN can list customers
    cust_list_tech = await async_client.get("/api/v1/customers", headers=tech_headers)
    assert cust_list_tech.status_code == 200
    assert len(cust_list_tech.json()) == 1

    create_resp = await async_client.post(
        "/api/v1/quotes",
        headers=owner_headers,
        json={
            "customer_id": customer_id,
            "valid_days": 10,
            "items": [
                {"catalog_item_id": str(dvr_mhdx.id), "quantity": 1},
                {"catalog_item_id": str(hdd_purple.id), "quantity": 1},
            ],
        },
    )
    assert create_resp.status_code == 201
    quote_id: str = create_resp.json()["id"]
    public_token: str = create_resp.json()["public_token"]

    # Send quote and approve via public endpoint
    await async_client.post(f"/api/v1/quotes/{quote_id}/send", headers=owner_headers)
    approve_resp = await async_client.post(
        f"/api/v1/public/quotes/{public_token}/approve",
        json={"accepted_terms": True, "client_notes": "Instalar no período da manhã."},
    )
    assert approve_resp.status_code == 200

    # 1. OWNER GET /api/v1/quotes/{id} includes cost, margin, and audit_logs
    owner_get = await async_client.get(f"/api/v1/quotes/{quote_id}", headers=owner_headers)
    assert owner_get.status_code == 200
    owner_quote_json = owner_get.json()
    assert owner_quote_json["total_cost_cents"] == 59000 + 39500
    assert owner_quote_json["total_sale_cents"] == 89900 + 59900
    assert "margin_percent" in owner_quote_json
    assert len(owner_quote_json["audit_logs"]) == 3
    assert all("unit_cost_cents" in item for item in owner_quote_json["items"])

    # 2. TECHNICIAN GET /api/v1/quotes/{id} strips cost and margin completely
    tech_get = await async_client.get(f"/api/v1/quotes/{quote_id}", headers=tech_headers)
    assert tech_get.status_code == 200
    tech_quote_json = tech_get.json()
    assert tech_quote_json["total_sale_cents"] == 89900 + 59900
    assert "total_cost_cents" not in tech_quote_json
    assert "margin_percent" not in tech_quote_json
    assert all("unit_cost_cents" not in item for item in tech_quote_json["items"])
    assert "cost" not in tech_get.text
    assert "margin" not in tech_get.text

    # 3. PUBLIC_CLIENT GET /api/v1/public/quotes/{public_token} strips cost and margin
    pub_get = await async_client.get(f"/api/v1/public/quotes/{public_token}")
    assert pub_get.status_code == 200
    assert "cost" not in pub_get.text
    assert "margin" not in pub_get.text

    # 4. Cancel the APPROVED quote -> releases reserved_quantity back to 0
    cancel_resp = await async_client.post(
        f"/api/v1/quotes/{quote_id}/cancel",
        headers=owner_headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELED"

    async with session_maker() as check_session:
        refreshed_dvr = await check_session.get(CatalogItem, dvr_mhdx.id)
        refreshed_hdd = await check_session.get(CatalogItem, hdd_purple.id)
        refreshed_quote = await check_session.get(Quote, UUID(quote_id))
        assert refreshed_dvr is not None
        assert refreshed_hdd is not None
        assert refreshed_quote is not None
        assert refreshed_dvr.reserved_quantity == 0
        assert refreshed_hdd.reserved_quantity == 0
        assert refreshed_quote.status == QuoteStatus.CANCELED
