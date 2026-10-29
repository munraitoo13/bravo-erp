"""Smoke tests for /api/v1/health, Correlation-ID propagation, and RFC 7807 Problem+JSON."""

from httpx import ASGITransport, AsyncClient

from src.main import app


async def test_health_check_returns_ok_and_generates_correlation_id() -> None:
    """Verify /api/v1/health returns 200 OK with typed payload and X-Correlation-ID header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    header_corr_id = response.headers.get("X-Correlation-ID")
    assert header_corr_id is not None
    assert header_corr_id.startswith("req_")

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "bravo-erp"
    assert payload["correlation_id"] == header_corr_id


async def test_health_check_preserves_incoming_correlation_id() -> None:
    """Verify incoming X-Correlation-ID header is preserved and echoed on response."""
    custom_corr_id = "req_custom_trace_id_0001"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/health",
            headers={"X-Correlation-ID": custom_corr_id},
        )

    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == custom_corr_id
    assert response.json()["correlation_id"] == custom_corr_id


async def test_domain_error_serializes_to_rfc7807_problem_json() -> None:
    """Verify DomainError subclasses serialize to RFC 7807 application/problem+json."""
    custom_corr_id = "req_rfc7807_probe_9999"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/health/error-probe",
            headers={"X-Correlation-ID": custom_corr_id},
        )

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers.get("X-Correlation-ID") == custom_corr_id

    problem = response.json()
    assert problem["type"] == "https://bravo-erp.dev/errors/resource-not-found"
    assert problem["title"] == "Resource Not Found"
    assert problem["status"] == 404
    assert "dvr_mhdx_probe" in problem["detail"]
    assert problem["instance"] == "/api/v1/health/error-probe"
    assert problem["correlation_id"] == custom_corr_id
    assert problem["errors"] == [{"resource": "dvr_mhdx_probe", "reason": "probe_verification"}]
