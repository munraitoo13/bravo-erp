"""Integration tests for multi-tenant isolation, RBAC redaction, Demo Seed protection, and Auth."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import UserRole, hash_password
from src.modules.catalog.models import CatalogCategory, CatalogItem
from src.modules.tenants.models import Organization, User


async def _create_tenant_with_owner_and_sku(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    cnpj: str,
    owner_email: str,
    password: str,
    sku: str,
) -> tuple[Organization, User, CatalogItem]:
    """Create an isolated tenant, OWNER user, and CatalogItem for cross-tenant tests."""
    org = Organization(
        name=name,
        slug=slug,
        document_cnpj=cnpj,
        is_demo=False,
    )
    session.add(org)
    await session.flush()

    owner = User(
        organization_id=org.id,
        email=owner_email,
        password_hash=hash_password(password),
        full_name=f"Owner {name}",
        role=UserRole.OWNER,
        is_active=True,
    )
    session.add(owner)

    item = CatalogItem(
        organization_id=org.id,
        sku=sku,
        name_pt_br=f"Câmera Exclusiva {name}",
        category=CatalogCategory.CAMERA_ANALOG,
        brand="Intelbras",
        cost_price_cents=12000,
        sale_price_cents=21000,
        stock_quantity=10,
        reserved_quantity=0,
        specs={
            "resolution": "1080p",
            "max_fps": 30,
            "ir_range_meters": 20,
            "ir_current_draw_ma": 350,
            "nominal_voltage_vdc": 12.0,
            "min_operating_voltage_vdc": 10.8,
            "form_factor": "BULLET",
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
        is_seed_protected=False,
        is_active=True,
    )
    session.add(item)
    await session.commit()
    return org, owner, item


async def test_demo_login_personas_and_rbac_cost_stripping(
    async_client: AsyncClient,
) -> None:
    """Verify 1-Click Demo Login for all 3 personas and RBAC cost stripping on /api/v1/catalog."""
    # 1. Demo Login as OWNER
    owner_resp = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "OWNER"},
    )
    assert owner_resp.status_code == 200
    owner_data = owner_resp.json()
    assert owner_data["persona"] == "OWNER"
    assert owner_data["access_token"] is not None
    assert owner_data["organization"]["name"] == "Bravo Segurança Eletrônica Ltda"
    assert owner_data["redirect_path"] == "/dashboard"
    owner_token: str = owner_data["access_token"]

    # Verify /api/v1/auth/me works with OWNER token
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["role"] == "OWNER"

    # Verify OWNER sees cost_price_cents in /api/v1/catalog
    owner_catalog_resp = await async_client.get(
        "/api/v1/catalog",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owner_catalog_resp.status_code == 200
    owner_items = owner_catalog_resp.json()
    assert len(owner_items) == 31
    assert all("cost_price_cents" in item for item in owner_items)

    # 2. Demo Login as TECHNICIAN
    tech_resp = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "TECHNICIAN"},
    )
    assert tech_resp.status_code == 200
    tech_data = tech_resp.json()
    assert tech_data["persona"] == "TECHNICIAN"
    assert tech_data["access_token"] is not None
    assert tech_data["redirect_path"] == "/work-orders"
    tech_token: str = tech_data["access_token"]

    # Verify TECHNICIAN does NOT see cost_price_cents in /api/v1/catalog
    tech_catalog_resp = await async_client.get(
        "/api/v1/catalog",
        headers={"Authorization": f"Bearer {tech_token}"},
    )
    assert tech_catalog_resp.status_code == 200
    tech_items = tech_catalog_resp.json()
    assert len(tech_items) == 31
    assert all("cost_price_cents" not in item for item in tech_items)

    # Verify TECHNICIAN is blocked from creating catalog items (403 Problem+JSON)
    tech_create_resp = await async_client.post(
        "/api/v1/catalog",
        headers={"Authorization": f"Bearer {tech_token}"},
        json={
            "sku": "TECH-FORBIDDEN-SKU",
            "name_pt_br": "Item Não Autorizado",
            "category": "BALUN",
            "brand": "Intelbras",
            "cost_price_cents": 1000,
            "sale_price_cents": 2000,
            "stock_quantity": 5,
            "specs": {"sub_type": "PASSIVE_BALUN_PAIR", "units_per_package": 1},
        },
    )
    assert tech_create_resp.status_code == 403
    assert tech_create_resp.headers["content-type"].startswith("application/problem+json")
    assert tech_create_resp.json()["type"].endswith("/role-permission-denied")

    # 3. Demo Login as PUBLIC_CLIENT
    public_resp = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "PUBLIC_CLIENT"},
    )
    assert public_resp.status_code == 200
    public_data = public_resp.json()
    assert public_data["persona"] == "PUBLIC_CLIENT"
    assert public_data["access_token"] is None
    assert public_data["redirect_path"].startswith("/public/quotes/")


async def test_demo_seed_protection_blocks_deletion_with_403_problem_json(
    async_client: AsyncClient,
) -> None:
    """Verify deleting an is_seed_protected Demo catalog item returns 403 DemoProtectionError."""
    owner_resp = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "OWNER"},
    )
    owner_token: str = owner_resp.json()["access_token"]

    catalog_resp = await async_client.get(
        "/api/v1/catalog",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    mhdx_item = next(item for item in catalog_resp.json() if item["sku"] == "MHDX-1108")
    assert mhdx_item["is_seed_protected"] is True

    delete_resp = await async_client.delete(
        f"/api/v1/catalog/{mhdx_item['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert delete_resp.status_code == 403
    assert delete_resp.headers["content-type"].startswith("application/problem+json")
    problem = delete_resp.json()
    assert problem["type"] == "https://bravo-erp.dev/errors/demo-seed-protected"
    assert problem["status"] == 403
    assert "MHDX-1108" in problem["detail"]


async def test_strict_multi_tenant_isolation_between_organization_a_and_organization_b(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify Organization A cannot read, update, or delete Organization B's catalog items."""
    _, _, item_a = await _create_tenant_with_owner_and_sku(
        db_session,
        name="Alpha Segurança Eletrônica Ltda",
        slug="alpha-seguranca",
        cnpj="11.111.111/0001-11",
        owner_email="owner@alphaseguranca.com.br",
        password="AlphaSecretPassword!1",
        sku="ALPHA-CAM-01",
    )
    _, _, item_b = await _create_tenant_with_owner_and_sku(
        db_session,
        name="Beta Monitoramento 24h Ltda",
        slug="beta-monitoramento",
        cnpj="22.222.222/0001-22",
        owner_email="owner@betamonitoramento.com.br",
        password="BetaSecretPassword!2",
        sku="BETA-CAM-01",
    )

    # Authenticate as Organization A OWNER
    login_a = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "owner@alphaseguranca.com.br",
            "password": "AlphaSecretPassword!1",
        },
    )
    assert login_a.status_code == 200
    token_a: str = login_a.json()["access_token"]

    # Organization A lists catalog: sees only ALPHA-CAM-01, never BETA-CAM-01
    list_a = await async_client.get(
        "/api/v1/catalog",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_a.status_code == 200
    skus_a = [item["sku"] for item in list_a.json()]
    assert skus_a == ["ALPHA-CAM-01"]

    # Organization A attempts GET on Organization B's item -> 404 Problem+JSON
    get_cross = await async_client.get(
        f"/api/v1/catalog/{item_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_cross.status_code == 404
    assert get_cross.headers["content-type"].startswith("application/problem+json")
    assert get_cross.json()["type"] == "https://bravo-erp.dev/errors/resource-not-found"

    # Organization A attempts PATCH on Organization B's item -> 404 Problem+JSON
    patch_cross = await async_client.patch(
        f"/api/v1/catalog/{item_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"sale_price_cents": 100},
    )
    assert patch_cross.status_code == 404

    # Organization A attempts DELETE on Organization B's item -> 404 Problem+JSON
    delete_cross = await async_client.delete(
        f"/api/v1/catalog/{item_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert delete_cross.status_code == 404

    # Organization A can update and soft-delete its own non-protected item
    patch_own = await async_client.patch(
        f"/api/v1/catalog/{item_a.id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"stock_quantity": 25},
    )
    assert patch_own.status_code == 200
    assert patch_own.json()["stock_quantity"] == 25

    delete_own = await async_client.delete(
        f"/api/v1/catalog/{item_a.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert delete_own.status_code == 204

    # Demo Reset does not affect Organization B
    reset_resp = await async_client.post("/api/v1/auth/demo-reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "reset_completed"
    assert reset_resp.json()["catalog_items_restored"] == 31

    login_b = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "owner@betamonitoramento.com.br",
            "password": "BetaSecretPassword!2",
        },
    )
    token_b: str = login_b.json()["access_token"]
    get_b = await async_client.get(
        f"/api/v1/catalog/{item_b.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert get_b.status_code == 200
    assert get_b.json()["sku"] == "BETA-CAM-01"


async def test_sizing_calculate_endpoint_hybrid_mhdx_and_rbac_redaction(
    async_client: AsyncClient,
) -> None:
    """Verify POST /api/v1/sizing/calculate computes MHDX hybrid BOM and strips cost for Tech."""
    owner_resp = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "OWNER"},
    )
    owner_token: str = owner_resp.json()["access_token"]

    tech_resp = await async_client.post(
        "/api/v1/auth/demo-login",
        json={"persona": "TECHNICIAN"},
    )
    tech_token: str = tech_resp.json()["access_token"]

    sizing_payload = {
        "camera_groups": [
            {
                "group_label": "7x Analógicas BNC Perímetro",
                "technology": "ANALOG",
                "count": 7,
                "resolution": "1080p",
                "fps": 30,
                "codec": "H.265+",
                "retention_days": 15,
                "cabling_mode": "BALUN_UTP",
                "average_cable_meters": 45.0,
                "form_factor": "BULLET",
            },
            {
                "group_label": "3x IP PoE Portaria",
                "technology": "IP",
                "count": 3,
                "resolution": "1080p",
                "fps": 30,
                "codec": "H.265+",
                "retention_days": 15,
                "cabling_mode": "UTP_CAT5E",
                "average_cable_meters": 40.0,
                "form_factor": "BULLET",
            },
        ]
    }

    # 1. OWNER calls /api/v1/sizing/calculate -> receives full cost & margin
    owner_sizing = await async_client.post(
        "/api/v1/sizing/calculate",
        headers={"Authorization": f"Bearer {owner_token}"},
        json=sizing_payload,
    )
    assert owner_sizing.status_code == 200
    owner_data = owner_sizing.json()
    assert owner_data["topology"]["selected_recorder_sku"] == "MHDX-1108"
    assert owner_data["topology"]["bnc_channels_converted_to_ip"] == 1
    assert owner_data["topology"]["total_cameras_count"] == 10
    assert "total_cost_cents" in owner_data
    assert "margin_percent" in owner_data
    assert all("unit_cost_cents" in line for line in owner_data["bom_items"])

    # 2. TECHNICIAN calls /api/v1/sizing/calculate -> cost & margin strictly omitted
    tech_sizing = await async_client.post(
        "/api/v1/sizing/calculate",
        headers={"Authorization": f"Bearer {tech_token}"},
        json=sizing_payload,
    )
    assert tech_sizing.status_code == 200
    tech_data = tech_sizing.json()
    assert tech_data["topology"]["selected_recorder_sku"] == "MHDX-1108"
    assert tech_data["total_sale_cents"] == owner_data["total_sale_cents"]
    assert "total_cost_cents" not in tech_data
    assert "margin_percent" not in tech_data
    assert all("unit_cost_cents" not in line for line in tech_data["bom_items"])
    assert all("line_total_cost_cents" not in line for line in tech_data["bom_items"])
    assert "cost" not in tech_sizing.text
    assert "margin_percent" not in tech_sizing.text
