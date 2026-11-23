"""Validação/normalização do payload de /api/narrativa (400 em vez de 500, sem '8500%')."""
import uuid

import pytest


def _cliente():
    import database as db
    from app import app
    db.init_db()
    email = f"narr_{uuid.uuid4().hex[:10]}@example.com"
    db.criar_usuario(email, "Narr", "senha123")
    uid = db.buscar_usuario_email(email)["id"]
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = str(uid)
    return c


@pytest.fixture
def prompts(monkeypatch):
    """Ativa a IA com um Groq falso que captura o prompt enviado."""
    import app as app_module
    import services.groq_narrativa as g

    capturados = []

    class _Resp:
        choices = [type("C", (), {"message": type("M", (), {"content": "Parecer ok."})()})()]

    class _Cliente:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    capturados.append(kw["messages"][0]["content"])
                    return _Resp()

    monkeypatch.setattr(app_module, "_narrativa_ativa", lambda: True)
    monkeypatch.setattr(g, "_feature_ativa", lambda: True)
    monkeypatch.setattr(g, "_groq_client", lambda: _Cliente())
    return capturados


def _ctx(**extra):
    base = {"tipo": "CRIA", "confianca": 0.85, "total_rebanho": 1200,
            "receita_anual": 3_500_000, "geracao_caixa_anual": 900_000,
            "recomendacao": "aprovar", "fazenda": "Faz. Teste"}
    base.update(extra)
    return base


@pytest.mark.parametrize("conf", [0.85, 85, 85.0, "85"])
def test_confianca_nas_duas_escalas_vira_85_pct(prompts, conf):
    r = _cliente().post("/api/narrativa", json={"contexto": _ctx(confianca=conf)})
    assert r.status_code == 200, r.get_json()
    assert "confiança ML: 85%" in prompts[-1]
    assert "8500%" not in prompts[-1]


def test_campos_nulos_ou_ausentes_usam_fallback(prompts):
    ctx = {"tipo": "CRIA", "confianca": None, "total_rebanho": None,
           "receita_anual": None, "geracao_caixa_anual": None,
           "recomendacao": None, "consistencia_score": None, "fazenda": None}
    r = _cliente().post("/api/narrativa", json={"contexto": ctx})
    assert r.status_code == 200, r.get_json()
    p = prompts[-1]
    assert "confiança ML: não informada" in p
    assert "sem solicitação de crédito" in p
    assert "None" not in p
    r = _cliente().post("/api/narrativa", json={"contexto": {"tipo": "CRIA"}})
    assert r.status_code == 200


@pytest.mark.parametrize("campo,valor", [
    ("confianca", "abc"), ("confianca", 150), ("confianca", -1), ("confianca", [1]),
    ("confianca", True), ("confianca", "nan"),
    ("total_rebanho", "muitos"), ("total_rebanho", -5),
    ("receita_anual", "R$ 1.000"), ("receita_anual", {"a": 1}),
    ("geracao_caixa_anual", "inf"), ("dscr", "x"), ("limite_credito", "x"),
    ("coe_por_arroba", [1]), ("consistencia_score", 500),
    ("receita_anual", 10**400), ("confianca", 10**400),
    ("recomendacao", ["aprovar"]), ("fazenda", 123), ("tipo", ["CRIA"]),
])
def test_valores_invalidos_retornam_400(prompts, campo, valor):
    r = _cliente().post("/api/narrativa", json={"contexto": _ctx(**{campo: valor})})
    assert r.status_code == 400, (campo, valor, r.status_code)
    assert "erro" in r.get_json()
    assert not prompts, "payload inválido não pode chegar ao Groq"


@pytest.mark.parametrize("corpo", [
    {"contexto": "texto"}, {"contexto": [1, 2]}, {"contexto": None}, [1, 2], "x",
])
def test_estrutura_invalida_retorna_400(prompts, corpo):
    r = _cliente().post("/api/narrativa", json=corpo)
    assert r.status_code == 400


def test_corpo_nao_json_retorna_400(prompts):
    r = _cliente().post("/api/narrativa", data="não é json",
                        content_type="application/json")
    assert r.status_code == 400


def test_textos_longos_sao_truncados(prompts):
    r = _cliente().post("/api/narrativa",
                        json={"contexto": _ctx(fazenda="F" * 5000)})
    assert r.status_code == 200
    assert "F" * 121 not in prompts[-1]


def test_contexto_str_normaliza_confianca_direto():
    from services.groq_narrativa import _contexto_str
    for c in (85, 0.85):
        assert "8500%" not in _contexto_str({"tipo": "CRIA", "confianca": c})
    assert "não informada" in _contexto_str({"tipo": "CRIA", "confianca": None})
    # contexto vindo do cliente no chat não pode levantar
    for ruim in (150, "abc", float("nan"), 10**400, [1]):
        assert "não informada" in _contexto_str({"tipo": "CRIA", "confianca": ruim})


def test_chat_com_confianca_invalida_nao_da_500(prompts):
    r = _cliente().post("/api/chat", json={"mensagem": "explique o parecer",
                                           "contexto": {"tipo": "CRIA", "confianca": 150}})
    assert r.status_code != 500
