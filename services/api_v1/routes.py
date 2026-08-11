from __future__ import annotations

import hashlib
import time
from copy import deepcopy

from flask import current_app, g, jsonify, request

import database as db
from services.analysis_pipeline import run_full_analysis
from services.cashflow_engine import project_cashflow
from services.engine.contracts import HerdState
from services.livestock_engine import analyze_herd
from services.payment_capacity_engine import calculate_payment_capacity
from services.production_engine import project_production
from services.stress_engine import run_stress_tests

from .authentication import APIKeyIdentity, authenticate_api_key
from .errors import ConflictError, NotFoundError, ValidationError
from .schemas import (
    load_json_body,
    parse_cashflow_payload,
    parse_full_analysis_payload,
    parse_herd_payload,
    parse_payment_capacity_payload,
    parse_production_payload,
    parse_stress_payload,
)
from . import api_v1_bp
from services.rate_limit import limiter


def _rate_limit_spec() -> str:
    value = current_app.config.get("API_V1_RATE_LIMIT", "120 per minute")
    if callable(value):
        value = value()
    return str(value)


def _rate_limit_key() -> str:
    raw_key = (
        request.headers.get("X-API-Key")
        or request.headers.get("Authorization")
        or request.remote_addr
        or ""
    ).strip()
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _check_rate_limit(scope: str) -> None:
    @limiter.limit(_rate_limit_spec, key_func=_rate_limit_key, scope=scope)
    def _noop():
        return None

    _noop()


def _requested_organization(body: dict | None) -> int | None:
    if not body:
        return None
    value = body.get("organization_id")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Field 'organization_id' must be an integer.") from exc


def _current_identity(*, scopes: tuple[str, ...] | list[str] = (), organization_id: int | None = None) -> APIKeyIdentity:
    identity = authenticate_api_key(
        required_scopes=scopes,
        organization_id=organization_id,
        request_organization_id=organization_id,
    )
    g.api_key_identity = identity
    return identity


def _analysis_payload_for_storage(body: dict) -> dict:
    payload = deepcopy(body)
    payload.pop("organization_id", None)
    payload.pop("user_id", None)
    return payload


def _stable_request_hash(body: dict) -> str:
    payload = _analysis_payload_for_storage(body)
    return hashlib.sha256(db._stable_json(payload).encode("utf-8")).hexdigest()


def _public_snapshot(snapshot: dict) -> dict:
    return {
        "id": snapshot["id"],
        "analysis_id": snapshot["id"],
        "organization_id": snapshot["organization_id"],
        "user_id": snapshot.get("user_id"),
        "payload": snapshot.get("payload", {}),
        "context": snapshot.get("context", {}),
        "result": snapshot.get("result", {}),
        "block_order": snapshot.get("block_order", []),
        "version": snapshot.get("version", {}),
        "created_at": snapshot.get("created_at", ""),
    }


def _report_payload(snapshot: dict) -> dict:
    result = snapshot.get("result", {})
    legacy = result.get("legacy_response") or {}
    summary = {
        "analysis_id": snapshot["id"],
        "organization_id": snapshot["organization_id"],
        "version": result.get("version", {}),
        "block_order": result.get("block_order", []),
        "quality_status": (legacy.get("qualidade_dados") or {}).get("status"),
        "recommended_action": ((legacy.get("analises_credito") or {}).get("conclusao") or {}).get("recomendacao"),
    }
    return {
        "summary": summary,
        "sections": legacy,
        "analysis": result.get("analysis", {}),
    }


def _openapi_document() -> dict:
    host_url = request.host_url.rstrip("/") if request else ""
    example_values = [120, 90, 80, 60, 50, 40, 30, 20, 10, 5]
    herd_request = {"valores": example_values, "bois_vendidos": 2}
    production_request = {"valores": example_values, "system": "CRIA", "years": 4, "parameters": {"preco_arroba": 320}}
    cashflow_request = {
        "annual_projection": {"anos": [{"ano": 1, "resultado": 12345, "custo": 5000, "receita": 17345}]},
        "debt_schedule": {"credito_valor": 50000, "juros_aa": 0.12, "prazo_meses": 24},
        "horizon_months": 12,
    }
    payment_request = {
        "cashflow": {"geracao_caixa_anual": 20000, "projecao_anos": [{"ano": 1, "resultado": 20000}]},
        "debt_request": {"credito_valor": 50000, "prazo_meses": 24, "juros_aa": 0.12},
    }
    stress_request = {"base_analysis": {"projecao_anos": [{"ano": 1, "resultado": 10000}]}}
    full_request = {"valores": example_values, "preco": 320, "organization_id": 17}
    error_schema = {
        "type": "object",
        "properties": {
            "error": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "details": {},
                },
                "required": ["code", "message"],
            },
            "trace_id": {"type": "string"},
        },
        "required": ["error", "trace_id"],
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Livestock Intelligence API",
            "version": "v1",
            "description": (
                "Versioned B2B API for livestock intelligence. "
                "Authenticate every request with X-API-Key or Authorization: Bearer. "
                "Requests that support replay must include Idempotency-Key."
            ),
        },
        "servers": [{"url": host_url or "/"}],
        "security": [{"ApiKeyAuth": []}, {"BearerAuth": []}],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "API key in the format lii_<prefix>.<secret>.",
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "API key",
                },
                "Authorization": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "API key",
                    "description": "Equivalent bearer header: Authorization: Bearer <api-key>.",
                },
            },
            "schemas": {
                "Error": error_schema,
            },
            "examples": {
                "HerdRequest": {"value": herd_request},
                "ProductionRequest": {"value": production_request},
                "CashflowRequest": {"value": cashflow_request},
                "PaymentRequest": {"value": payment_request},
                "StressRequest": {"value": stress_request},
                "FullAnalysisRequest": {"value": full_request},
            },
        },
        "paths": {
            "/api/v1/herd/analyze": {
                "post": {
                    "summary": "Analyze herd structure",
                    "security": [{"ApiKeyAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"},
                                "example": herd_request,
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Herd analysis"},
                        "400": {"description": "Malformed request", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                        "401": {"description": "Invalid API key"},
                        "403": {"description": "Forbidden"},
                    },
                }
            },
            "/api/v1/production/project": {
                "post": {
                    "summary": "Project production",
                    "security": [{"ApiKeyAuth": []}],
                    "requestBody": {"required": True, "content": {"application/json": {"example": production_request}}},
                    "responses": {"200": {"description": "Production projection"}},
                }
            },
            "/api/v1/cashflow/project": {
                "post": {
                    "summary": "Project cashflow",
                    "security": [{"ApiKeyAuth": []}],
                    "requestBody": {"required": True, "content": {"application/json": {"example": cashflow_request}}},
                    "responses": {"200": {"description": "Cashflow projection"}},
                }
            },
            "/api/v1/payment-capacity": {
                "post": {
                    "summary": "Assess payment capacity",
                    "security": [{"ApiKeyAuth": []}],
                    "requestBody": {"required": True, "content": {"application/json": {"example": payment_request}}},
                    "responses": {"200": {"description": "Payment capacity"}},
                }
            },
            "/api/v1/stress-test": {
                "post": {
                    "summary": "Run stress scenarios",
                    "security": [{"ApiKeyAuth": []}],
                    "requestBody": {"required": True, "content": {"application/json": {"example": stress_request}}},
                    "responses": {"200": {"description": "Stress test results"}},
                }
            },
            "/api/v1/full-analysis": {
                "post": {
                    "summary": "Run the full analysis pipeline",
                    "security": [{"ApiKeyAuth": []}],
                    "parameters": [
                        {"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {"required": True, "content": {"application/json": {"example": full_request}}},
                    "responses": {"200": {"description": "Persisted analysis"}},
                }
            },
            "/api/v1/analysis/{id}": {
                "get": {
                    "summary": "Retrieve a stored analysis",
                    "security": [{"ApiKeyAuth": []}],
                    "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {"200": {"description": "Stored analysis"}, "404": {"description": "Analysis not found"}},
                }
            },
            "/api/v1/report/{id}": {
                "get": {
                    "summary": "Retrieve a machine-readable report",
                    "security": [{"ApiKeyAuth": []}],
                    "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {"200": {"description": "Stored report"}, "404": {"description": "Analysis not found"}},
                }
            },
            "/api/docs": {
                "get": {
                    "summary": "OpenAPI document",
                    "responses": {"200": {"description": "OpenAPI JSON document"}},
                }
            },
        },
    }


@api_v1_bp.route("/api/v1/herd/analyze", methods=["POST"])
def herd_analyze():
    body = parse_herd_payload(load_json_body())
    identity = _current_identity(scopes=("herd:analyze",), organization_id=_requested_organization(body))
    _check_rate_limit("api.v1.herd.analyze")
    herd_state = HerdState(
        values=body["valores"],
        source="API",
        farm_id=body.get("fazenda_id"),
        metadata={
            key: body[key]
            for key in ("bois_vendidos", "bezerros_vendidos")
            if key in body
        },
    )
    result = analyze_herd(herd_state, ml_result=body.get("ml_result"))
    return jsonify({
        "organization_id": identity.organization_id,
        "api_key_id": identity.api_key_id,
        "herd": result,
    })


@api_v1_bp.route("/api/v1/production/project", methods=["POST"])
def production_project():
    body = parse_production_payload(load_json_body())
    identity = _current_identity(scopes=("production:project",), organization_id=_requested_organization(body))
    _check_rate_limit("api.v1.production.project")
    herd_state = HerdState(
        values=body["valores"],
        source="API",
        farm_id=body.get("fazenda_id"),
        metadata={
            key: body[key]
            for key in ("bois_vendidos", "bezerros_vendidos")
            if key in body
        },
    )
    result = project_production(herd_state, body["system"], body.get("parameters") or {}, years=body["years"])
    return jsonify({
        "organization_id": identity.organization_id,
        "api_key_id": identity.api_key_id,
        "production": result,
    })


@api_v1_bp.route("/api/v1/cashflow/project", methods=["POST"])
def cashflow_project():
    body = parse_cashflow_payload(load_json_body())
    identity = _current_identity(scopes=("cashflow:project",), organization_id=_requested_organization(body))
    _check_rate_limit("api.v1.cashflow.project")
    result = project_cashflow(
        body["annual_projection"],
        body["debt_schedule"],
        horizon_months=body["horizon_months"],
        calendar=body.get("calendar"),
        seasonality=body.get("seasonality"),
    )
    return jsonify({
        "organization_id": identity.organization_id,
        "api_key_id": identity.api_key_id,
        "cashflow": result,
    })


@api_v1_bp.route("/api/v1/payment-capacity", methods=["POST"])
def payment_capacity():
    body = parse_payment_capacity_payload(load_json_body())
    identity = _current_identity(scopes=("payment-capacity:analyze",), organization_id=_requested_organization(body))
    _check_rate_limit("api.v1.payment.capacity")
    result = calculate_payment_capacity(body["cashflow"], body["debt_request"], body.get("existing_debt"))
    return jsonify({
        "organization_id": identity.organization_id,
        "api_key_id": identity.api_key_id,
        "payment_capacity": result,
    })


@api_v1_bp.route("/api/v1/stress-test", methods=["POST"])
def stress_test():
    body = parse_stress_payload(load_json_body())
    identity = _current_identity(scopes=("stress:analyze",), organization_id=_requested_organization(body))
    _check_rate_limit("api.v1.stress.test")
    result = run_stress_tests(body["base_analysis"], body.get("scenarios"))
    return jsonify({
        "organization_id": identity.organization_id,
        "api_key_id": identity.api_key_id,
        "stress_test": result,
    })


@api_v1_bp.route("/api/v1/full-analysis", methods=["POST"])
def full_analysis():
    body = parse_full_analysis_payload(load_json_body())
    organization_id = _requested_organization(body)
    identity = _current_identity(scopes=("analysis:write",), organization_id=organization_id)
    _check_rate_limit("api.v1.full.analysis")
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
    if not idempotency_key:
        raise ValidationError("Header 'Idempotency-Key' is required.")

    analysis_input = _analysis_payload_for_storage(body)
    reservation = db.reserve_analysis_idempotency(
        organization_id=identity.organization_id,
        idempotency_key=idempotency_key,
        request=analysis_input,
    )
    request_hash = _stable_request_hash(body)
    if not reservation.get("created"):
        if reservation["request_hash"] != request_hash:
            raise ConflictError(
                "Idempotency key already exists for a different request.",
                details={"idempotency_key": idempotency_key},
            )
        response = deepcopy(reservation["response"])
        if response and reservation.get("analysis_id") is not None:
            response.setdefault("organization_id", identity.organization_id)
            response.setdefault("analysis_id", reservation.get("analysis_id"))
            return jsonify(response)

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = db.load_analysis_idempotency(
                organization_id=identity.organization_id,
                idempotency_key=idempotency_key,
            )
            if current and current["request_hash"] == request_hash and current.get("analysis_id") is not None and current.get("response"):
                response = deepcopy(current["response"])
                response.setdefault("organization_id", identity.organization_id)
                response.setdefault("analysis_id", current.get("analysis_id"))
                return jsonify(response)
            time.sleep(0.05)
        raise ConflictError(
            "Analysis is still being processed.",
            details={"idempotency_key": idempotency_key},
        )

    context = {
        "organization_id": identity.organization_id,
        "user_id": identity.user_id,
        "api_key_id": identity.api_key_id,
    }
    analysis = run_full_analysis(analysis_input, context)
    snapshot_id = db.save_analysis_snapshot(
        organization_id=identity.organization_id,
        user_id=identity.user_id,
        payload=analysis.get("payload", analysis_input),
        context=context,
        result=analysis,
        version=analysis.get("version"),
    )
    response = {
        "organization_id": identity.organization_id,
        "analysis_id": snapshot_id,
        "analysis": analysis,
        "version": analysis.get("version", {}),
        "context": context,
    }
    db.save_analysis_idempotency(
        organization_id=identity.organization_id,
        idempotency_key=idempotency_key,
        request=analysis_input,
        response=response,
        analysis_id=snapshot_id,
    )
    return jsonify(response)


@api_v1_bp.route("/api/v1/analysis/<int:analysis_id>", methods=["GET"])
def analysis_retrieve(analysis_id: int):
    identity = _current_identity(scopes=("analysis:read",))
    _check_rate_limit("api.v1.analysis.retrieve")
    snapshot = db.load_analysis_snapshot(analysis_id, organization_id=identity.organization_id)
    if not snapshot:
        raise NotFoundError("Analysis not found.", code="analysis_not_found", details={"analysis_id": analysis_id})
    payload = _public_snapshot(snapshot)
    return jsonify({
        "organization_id": identity.organization_id,
        "analysis_id": analysis_id,
        "analysis": payload["result"],
    })


@api_v1_bp.route("/api/v1/report/<int:analysis_id>", methods=["GET"])
def report_retrieve(analysis_id: int):
    identity = _current_identity(scopes=("report:read",))
    _check_rate_limit("api.v1.report.retrieve")
    snapshot = db.load_analysis_snapshot(analysis_id, organization_id=identity.organization_id)
    if not snapshot:
        raise NotFoundError("Analysis not found.", code="analysis_not_found", details={"analysis_id": analysis_id})
    payload = _public_snapshot(snapshot)
    return jsonify({
        "organization_id": identity.organization_id,
        "analysis_id": analysis_id,
        "report": _report_payload(payload),
    })


@api_v1_bp.route("/api/docs", methods=["GET"])
def api_docs():
    return jsonify(_openapi_document())
