from __future__ import annotations

import threading
import time
import uuid

import database as db
import pytest

import services.api_v1.routes as v1routes
from app import app


HerdPayload = {
    "valores": [120, 90, 80, 60, 50, 40, 30, 20, 10, 5],
    "bois_vendidos": 2,
    "bezerros_vendidos": 3,
}


def _create_user(prefix: str):
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    db.criar_usuario(email, prefix.title(), "senha123")
    user = db.buscar_usuario_email(email)
    org = db.empresas_do_usuario(user["id"])[0]
    return user, org


@pytest.fixture()
def api_env():
    db.init_db()
    user1, org1 = _create_user("api-v1-a")
    user2, org2 = _create_user("api-v1-b")
    client = app.test_client()
    return {
        "client": client,
        "user1": user1,
        "org1": org1,
        "user2": user2,
        "org2": org2,
    }


def _issue_key(org_id: int, *, scopes: list[str] | None = None, user_id: int | None = None):
    issued = db.issue_analysis_api_key(
        organization_id=org_id,
        user_id=user_id,
        name="Test key",
        scopes=scopes or [],
    )
    return issued["raw_key"], issued["id"]


def _auth_headers(raw_key: str, *, idempotency_key: str | None = None):
    headers = {"X-API-Key": raw_key}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def test_api_key_auth_scope_and_revocation_enforced(api_env, monkeypatch):
    raw_key, key_id = _issue_key(api_env["org1"]["id"], scopes=["herd:analyze"], user_id=api_env["user1"]["id"])
    raw_other, _ = _issue_key(api_env["org2"]["id"], scopes=["full-analysis"], user_id=api_env["user2"]["id"])

    monkeypatch.setattr(v1routes, "analyze_herd", lambda state, ml_result=None: {
        "system": "CRIA",
        "ok": True,
        "indicators": {"total_animals": len(state.values)},
    })

    ok = api_env["client"].post(
        "/api/v1/herd/analyze",
        json={"valores": HerdPayload["valores"]},
        headers=_auth_headers(raw_key),
    )
    assert ok.status_code == 200
    assert ok.get_json()["organization_id"] == api_env["org1"]["id"]

    malformed = api_env["client"].post(
        "/api/v1/herd/analyze",
        json={"valores": HerdPayload["valores"]},
        headers={"X-API-Key": "not-a-valid-key"},
    )
    assert malformed.status_code == 401
    assert malformed.get_json()["error"]["code"] == "malformed_api_key"

    forbidden = api_env["client"].post(
        "/api/v1/full-analysis",
        json={"organization_id": api_env["org1"]["id"], "valores": HerdPayload["valores"]},
        headers=_auth_headers(raw_other),
    )
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"]["code"] == "forbidden_organization"

    db.revoke_analysis_api_key(key_id, organization_id=api_env["org1"]["id"])
    revoked = api_env["client"].post(
        "/api/v1/herd/analyze",
        json={"valores": HerdPayload["valores"]},
        headers=_auth_headers(raw_key),
    )
    assert revoked.status_code == 401
    assert revoked.get_json()["error"]["code"] == "revoked_api_key"


def test_v1_endpoints_use_existing_engines_and_legacy_routes_stay_working(api_env, monkeypatch):
    monkeypatch.setattr(v1routes, "analyze_herd", lambda state, ml_result=None: {"system": "CRIA", "score": 99})
    monkeypatch.setattr(v1routes, "project_production", lambda state, system, parameters, years=5: {
        "system": system,
        "years": years,
        "parameters": parameters,
        "projected": True,
    })
    monkeypatch.setattr(v1routes, "project_cashflow", lambda annual_projection, debt_schedule, **kwargs: {
        "projection": annual_projection,
        "debt_schedule": debt_schedule,
        **kwargs,
    })
    monkeypatch.setattr(v1routes, "calculate_payment_capacity", lambda cashflow, debt_request, existing_debt=None: {
        "analysis": {
            "dscr_minimo": 1.42,
            "cashflow": cashflow,
            "debt_request": debt_request,
            "existing_debt": existing_debt or {},
        }
    })
    monkeypatch.setattr(v1routes, "run_stress_tests", lambda base_analysis, scenarios=None: {
        "base_analysis": base_analysis,
        "scenarios": scenarios or [],
    })

    herd = api_env["client"].post(
        "/api/v1/herd/analyze",
        json={"valores": HerdPayload["valores"]},
        headers=_auth_headers(_issue_key(api_env["org1"]["id"], scopes=["herd:analyze"])[0]),
    )
    assert herd.status_code == 200
    assert herd.get_json()["herd"]["system"] == "CRIA"

    production = api_env["client"].post(
        "/api/v1/production/project",
        json={"valores": HerdPayload["valores"], "system": "CRIA", "years": 4, "parameters": {"preco_arroba": 310}},
        headers=_auth_headers(_issue_key(api_env["org1"]["id"], scopes=["production:project"])[0]),
    )
    assert production.status_code == 200
    assert production.get_json()["production"]["projected"] is True

    cashflow = api_env["client"].post(
        "/api/v1/cashflow/project",
        json={"annual_projection": {"anos": [{"ano": 1, "resultado": 12_345}]}, "debt_schedule": {"credito_valor": 10_000}, "horizon_months": 12},
        headers=_auth_headers(_issue_key(api_env["org1"]["id"], scopes=["cashflow:project"])[0]),
    )
    assert cashflow.status_code == 200
    assert cashflow.get_json()["cashflow"]["projection"]["anos"][0]["resultado"] == 12345

    payment = api_env["client"].post(
        "/api/v1/payment-capacity",
        json={"cashflow": {"geracao_caixa_anual": 20_000, "projecao_anos": [{"ano": 1, "resultado": 20_000}]}, "debt_request": {"credito_valor": 50_000, "prazo_meses": 24, "juros_aa": 0.12}},
        headers=_auth_headers(_issue_key(api_env["org1"]["id"], scopes=["payment-capacity:analyze"])[0]),
    )
    assert payment.status_code == 200
    assert payment.get_json()["payment_capacity"]["analysis"]["dscr_minimo"] == 1.42

    stress = api_env["client"].post(
        "/api/v1/stress-test",
        json={"base_analysis": {"projecao_anos": [{"ano": 1, "resultado": 10_000}]}, "scenarios": [{"nome": "queda"}]},
        headers=_auth_headers(_issue_key(api_env["org1"]["id"], scopes=["stress:analyze"])[0]),
    )
    assert stress.status_code == 200
    assert stress.get_json()["stress_test"]["scenarios"][0]["nome"] == "queda"

    with api_env["client"].session_transaction() as session:
        session["_user_id"] = str(api_env["user1"]["id"])
    legacy = api_env["client"].post(
        "/api/classificar",
        json={"valores": HerdPayload["valores"], "preco": 320},
    )
    assert legacy.status_code == 200


def test_full_analysis_idempotency_and_retrieval(api_env, monkeypatch):
    calls = {"count": 0}

    def _pipeline(payload, context):
        calls["count"] += 1
        return {
            "version": {"schema_version": "1"},
            "context": context,
            "payload": payload,
            "blocks": [{"name": "herd", "output": {"system": "CRIA"}, "version": {"schema_version": "1"}}],
            "analysis": {"herd": {"system": "CRIA"}},
            "legacy_response": {"qualidade_dados": {"status": "COMPLETO"}},
            "block_order": ["herd"],
            "warnings": {},
        }

    monkeypatch.setattr(v1routes, "run_full_analysis", _pipeline)
    raw_key, _ = _issue_key(api_env["org1"]["id"], scopes=["analysis:write", "analysis:read", "report:read"])
    headers = _auth_headers(raw_key, idempotency_key="same-request-key")
    body = {"valores": HerdPayload["valores"], "preco": 320}

    first = api_env["client"].post("/api/v1/full-analysis", json=body, headers=headers)
    second = api_env["client"].post("/api/v1/full-analysis", json=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1
    assert first.get_json()["analysis_id"] == second.get_json()["analysis_id"]

    analysis_id = first.get_json()["analysis_id"]
    analysis = api_env["client"].get(
        f"/api/v1/analysis/{analysis_id}",
        headers=_auth_headers(raw_key),
    )
    assert analysis.status_code == 200
    assert analysis.get_json()["analysis"]["legacy_response"]["qualidade_dados"]["status"] == "COMPLETO"

    report = api_env["client"].get(
        f"/api/v1/report/{analysis_id}",
        headers=_auth_headers(raw_key),
    )
    assert report.status_code == 200
    assert report.get_json()["report"]["summary"]["analysis_id"] == analysis_id


def test_full_analysis_idempotency_deduplicates_concurrent_requests(api_env, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls = {"count": 0}

    def _pipeline(payload, context):
        calls["count"] += 1
        started.set()
        assert release.wait(timeout=5), "pipeline did not get released in time"
        return {
            "version": {"schema_version": "1"},
            "context": context,
            "payload": payload,
            "blocks": [{"name": "herd", "output": {"system": "CRIA"}, "version": {"schema_version": "1"}}],
            "analysis": {"herd": {"system": "CRIA"}},
            "legacy_response": {"qualidade_dados": {"status": "COMPLETO"}},
            "block_order": ["herd"],
            "warnings": {},
        }

    monkeypatch.setattr(v1routes, "run_full_analysis", _pipeline)
    raw_key, _ = _issue_key(api_env["org1"]["id"], scopes=["analysis:write", "analysis:read", "report:read"])
    headers = _auth_headers(raw_key, idempotency_key="concurrent-request")
    body = {"valores": HerdPayload["valores"], "preco": 320}

    results: dict[str, object] = {}

    def _post(label: str):
        client = app.test_client()
        results[label] = client.post("/api/v1/full-analysis", json=body, headers=headers)

    first = threading.Thread(target=_post, args=("first",))
    second = threading.Thread(target=_post, args=("second",))

    first.start()
    assert started.wait(timeout=5), "first request never entered the pipeline"
    second.start()
    time.sleep(0.15)
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert calls["count"] == 1
    assert "first" in results and "second" in results

    first_response = results["first"]
    second_response = results["second"]
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.get_json()["analysis_id"] == second_response.get_json()["analysis_id"]


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_v1_rejects_non_finite_numbers_in_required_arrays(api_env, literal):
    raw_key, _ = _issue_key(api_env["org1"]["id"], scopes=["herd:analyze"])
    payload = (
        '{"valores":[%s,0,0,0,0,0,0,0,0,10]}'
        % literal
    )
    response = api_env["client"].post(
        "/api/v1/herd/analyze",
        data=payload,
        headers=_auth_headers(raw_key),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_v1_rejects_non_finite_numbers_in_optional_scalars(api_env, literal):
    raw_key, _ = _issue_key(api_env["org1"]["id"], scopes=["herd:analyze"])
    payload = (
        '{"valores":[0,0,0,0,0,0,0,0,0,10],"taxa_natalidade":%s}'
        % literal
    )
    response = api_env["client"].post(
        "/api/v1/herd/analyze",
        data=payload,
        headers=_auth_headers(raw_key),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_v1_rate_limit_survives_local_cache_reset(api_env, monkeypatch):
    monkeypatch.setattr(v1routes, "analyze_herd", lambda state, ml_result=None: {"system": "CRIA", "score": 99})
    raw_key, _ = _issue_key(api_env["org1"]["id"], scopes=["herd:analyze"])
    headers = _auth_headers(raw_key)

    app.config["API_V1_RATE_LIMIT"] = "1 per minute"
    first = api_env["client"].post("/api/v1/herd/analyze", json={"valores": HerdPayload["valores"]}, headers=headers)
    assert first.status_code == 200

    local_cache = getattr(v1routes, "_RATE_BUCKETS", None)
    if local_cache is not None:
        local_cache.clear()
    second = api_env["client"].post("/api/v1/herd/analyze", json={"valores": HerdPayload["valores"]}, headers=headers)
    assert second.status_code == 429
    assert second.get_json()["error"]["code"] == "rate_limited"


def test_v1_errors_docs_and_rate_limit_are_machine_readable(api_env, monkeypatch):
    monkeypatch.setattr(v1routes, "analyze_herd", lambda state, ml_result=None: {"system": "CRIA"})
    raw_key, _ = _issue_key(api_env["org1"]["id"], scopes=["herd:analyze"])
    headers = _auth_headers(raw_key)

    app.config["API_V1_RATE_LIMIT"] = "2 per minute"
    first = api_env["client"].post("/api/v1/herd/analyze", json={"valores": HerdPayload["valores"]}, headers=headers)
    second = api_env["client"].post("/api/v1/herd/analyze", json={"valores": HerdPayload["valores"]}, headers=headers)
    third = api_env["client"].post("/api/v1/herd/analyze", json={"valores": HerdPayload["valores"]}, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.get_json()["error"]["code"] == "rate_limited"

    malformed = api_env["client"].post(
        "/api/v1/herd/analyze",
        data="not json",
        headers=headers,
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["code"] == "malformed_request"

    raw_read, _ = _issue_key(api_env["org1"]["id"], scopes=["analysis:read"])
    missing = api_env["client"].get(
        "/api/v1/analysis/999999",
        headers=_auth_headers(raw_read),
    )
    assert missing.status_code == 404
    assert missing.get_json()["error"]["code"] == "analysis_not_found"

    docs = api_env["client"].get("/api/docs")
    assert docs.status_code == 200
    spec = docs.get_json()
    assert spec["openapi"].startswith("3.")
    assert "/api/v1/full-analysis" in spec["paths"]
    assert "ApiKeyAuth" in spec["components"]["securitySchemes"]
    assert "Authorization" in spec["components"]["securitySchemes"]


def test_v1_rate_limit_uses_the_authenticated_api_key_identity(api_env, monkeypatch):
    monkeypatch.setattr(v1routes, "analyze_herd", lambda state, ml_result=None: {"system": "CRIA", "score": 99})
    monkeypatch.setitem(app.config, "API_V1_RATE_LIMIT", "1 per minute")

    raw_key, _ = _issue_key(api_env["org1"]["id"], scopes=["herd:analyze"])
    herd_body = {"valores": HerdPayload["valores"]}

    first = api_env["client"].post(
        "/api/v1/herd/analyze",
        json=herd_body,
        headers={"X-API-Key": raw_key},
    )
    assert first.status_code == 200

    second = api_env["client"].post(
        "/api/v1/herd/analyze",
        json=herd_body,
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert second.status_code == 429
    assert second.get_json()["error"]["code"] == "rate_limited"
