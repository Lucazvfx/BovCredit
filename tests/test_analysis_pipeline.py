from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import database as db
import pytest

import app as app_module
import services.analysis_pipeline as pipeline
from app import app
from services.engine.versions import engine_version


PAYLOAD = {
    "valores": [300, 280, 563, 187, 1105, 1344, 298, 80, 593, 39],
    "preco": 320,
    "credito_valor": 200_000,
    "prazo_meses": 36,
    "juros_aa": 0.11,
}


def _client():
    db.init_db()
    email = "pipeline_test@example.com"
    user = db.buscar_usuario_email(email)
    if not user:
        db.criar_usuario(email, "Pipeline Test", "senha123")
        user = db.buscar_usuario_email(email)
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user["id"])
    return client


def test_run_full_analysis_executes_blocks_in_order_and_attaches_version_metadata(monkeypatch):
    calls: list[str] = []

    def _block(name: str):
        def _impl(*args, **kwargs):
            calls.append(name)
            return {"name": name, "output": {"ok": name}, "version": engine_version()}

        return _impl

    monkeypatch.setattr(pipeline, "_build_validation_block", _block("validation"))
    monkeypatch.setattr(pipeline, "_build_herd_block", _block("herd"))
    monkeypatch.setattr(pipeline, "_build_production_block", _block("production"))
    monkeypatch.setattr(pipeline, "_build_economic_block", _block("economic"))
    monkeypatch.setattr(pipeline, "_build_cashflow_block", _block("cashflow"))
    monkeypatch.setattr(pipeline, "_build_debt_block", _block("debt"))
    monkeypatch.setattr(pipeline, "_build_stress_block", _block("stress"))
    monkeypatch.setattr(pipeline, "_build_quality_block", _block("quality"))
    monkeypatch.setattr(pipeline, "_build_explanation_block", _block("explanation"))

    result = pipeline.run_full_analysis(PAYLOAD, {"organization_id": 17, "user_id": 41})

    assert calls == [
        "validation",
        "herd",
        "production",
        "economic",
        "cashflow",
        "debt",
        "stress",
        "quality",
        "explanation",
    ]
    assert [block["name"] for block in result["blocks"]] == calls
    assert result["version"] == engine_version()
    assert all(block["version"] == engine_version() for block in result["blocks"])
    assert result["context"]["organization_id"] == 17
    assert result["context"]["user_id"] == 41


def test_herd_block_uses_legacy_default_when_taxa_natalidade_is_omitted(monkeypatch):
    captured: dict[str, object] = {}

    def _classificar(values, **kwargs):
        captured.update(kwargs)
        return {
            "tipo": "CRIA",
            "classificacao": "CRIA",
            "confianca": 92.0,
            "origem_decisao": "ml",
            "regra_aplicada": None,
        }

    monkeypatch.setattr(pipeline, "classificar", _classificar)
    monkeypatch.setattr(pipeline, "calcular_indicadores", lambda values: {"total_animals": sum(values)})
    monkeypatch.setattr(pipeline, "montar_explicacao_classificacao", lambda classification, indicators: {"ok": True})
    monkeypatch.setattr(pipeline, "analyze_herd", lambda herd_state, ml_result=None: {"ok": True})

    block = pipeline._build_herd_block({"valores": PAYLOAD["valores"]}, {}, {})

    assert "taxa_natalidade" not in captured
    assert block["output"]["classification"]["tipo"] == "CRIA"


def test_normalize_payload_maps_preco_into_preco_arroba():
    normalized = pipeline._normalize_payload({"valores": PAYLOAD["valores"], "preco": 344})

    assert normalized["preco"] == 344
    assert normalized["preco_arroba"] == 344


def test_snapshot_round_trip_is_immutable_and_organization_scoped(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis_snapshots.db"
    monkeypatch.setattr(db, "_DB_PATH", str(db_path))
    db.init_db()

    analysis = {
        "blocks": [
            {"name": "validation", "output": {"ok": True}, "version": engine_version()},
            {"name": "herd", "output": {"system": "CRIA"}, "version": engine_version()},
        ],
        "legacy_response": {"qualidade_dados": {"status": "COMPLETO"}},
        "version": engine_version(),
    }
    original = deepcopy(analysis)

    snapshot_id = db.save_analysis_snapshot(
        organization_id=7,
        user_id=11,
        payload={"valores": [1, 2, 3]},
        context={"organization_id": 7, "user_id": 11},
        result=analysis,
        version=engine_version(),
    )

    loaded = db.load_analysis_snapshot(snapshot_id, organization_id=7, user_id=11)
    assert loaded is not None
    assert loaded["organization_id"] == 7
    assert loaded["user_id"] == 11
    assert loaded["result"] == original
    assert loaded["version"] == engine_version()

    analysis["blocks"][0]["name"] = "changed"
    analysis["legacy_response"]["qualidade_dados"]["status"] = "ALTERADO"

    reloaded = db.load_analysis_snapshot(snapshot_id, organization_id=7, user_id=11)
    assert reloaded["result"] == original
    assert db.load_analysis_snapshot(snapshot_id, organization_id=8, user_id=11) is None
    assert db.load_analysis_snapshot(snapshot_id, organization_id=7, user_id=12) is None


def test_api_classificar_keeps_legacy_fields_after_pipeline_work(client=None):
    client = client or _client()
    response = client.post("/api/classificar", json=PAYLOAD)
    assert response.status_code == 200
    data = response.get_json()

    for field in (
        "qualidade_dados",
        "explicacao_classificacao",
        "validacoes_zootecnicas",
        "comparacao_cenarios",
        "fluxo_mensal",
        "rating",
        "fluxo_gep",
        "analises_credito",
        "projecao_anos",
        "desfrute_projetado",
    ):
        assert field in data

    assert data["qualidade_dados"]["campos"]
    assert data["analises_credito"]["capacidade_pagamento"]["dscr"] is not None
    assert data["desfrute_projetado"]["origem"] in {"informado", "projetado"}


def test_api_classificar_does_not_swallow_pipeline_errors(monkeypatch):
    client = _client()
    app_module.app.config["TESTING"] = True

    def _explode(*args, **kwargs):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(app_module, "run_full_analysis", _explode)

    response = client.post("/api/classificar", json=PAYLOAD)
    assert response.status_code == 500
