"""Gate de confiança do risco de crédito (0–100, limiar 70) e narrativa com
recomendacao=None (análise sem solicitação de crédito)."""
import uuid

import pytest

SEM_CREDITO = {"valores": [10, 10, 8, 8, 6, 6, 30, 2, 40, 3], "preco": 320, "custo_arroba": 57}


def _cliente():
    import database as db
    from app import app
    db.init_db()
    email = f"conf_{uuid.uuid4().hex[:10]}@example.com"
    db.criar_usuario(email, "Conf", "senha123")
    uid = db.buscar_usuario_email(email)["id"]
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = str(uid)
    return c


def _status_risco(confianca):
    """Roda /api/classificar forçando a confiança do classificador (0–100)."""
    import app as app_module
    original = app_module.classificar
    original_cons = app_module.analisar_consistencia

    def forcado(*a, **kw):
        r = original(*a, **kw)
        r["confianca"] = confianca
        return r

    def consistencia_limpa(*a, **kw):
        # isola o gate de confiança: sem alertas/erros e score alto
        c = original_cons(*a, **kw)
        c["score_consistencia"] = 100
        c["resumo"] = {"alertas": 0, "erros": 0}
        return c

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(app_module, "classificar", forcado)
        mp.setattr(app_module, "analisar_consistencia", consistencia_limpa)
        r = _cliente().post("/api/classificar", json=SEM_CREDITO)
    finally:
        mp.undo()
    assert r.status_code == 200, r.status_code
    return r.get_json()["analises_credito"]["risco_credito"]["status"]


def test_confianca_abaixo_de_70_pct_nao_e_risco_baixo():
    # Antes: _conf >= 0.70 com _conf em 0–100 deixava até 5% passar.
    assert _status_risco(5.0) != "baixo"
    assert _status_risco(69.9) != "baixo"


def test_confianca_a_partir_de_70_pct_libera_risco_baixo():
    assert _status_risco(70.0) == "baixo"
    assert _status_risco(95.0) == "baixo"


@pytest.mark.parametrize("rec", [None, "", "aprovar", "ressalva", "negar", "outro"])
def test_contexto_str_aceita_recomendacao_nula(rec):
    from services.groq_narrativa import _contexto_str
    txt = _contexto_str({"tipo": "CRIA", "confianca": 0.5, "recomendacao": rec})
    assert "Parecer final:" in txt
    if rec is None or rec == "":
        assert "sem solicitação de crédito" in txt
    if rec == "aprovar":
        assert "Parecer final: APROVADO" in txt
    if rec == "outro":
        assert "Parecer final: OUTRO" in txt


def test_gerar_narrativa_com_recomendacao_none_nao_levanta(monkeypatch):
    import services.groq_narrativa as g

    capturado = {}

    class _Msg:
        content = "texto"

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    capturado.update(kw)
                    return _Resp()

    monkeypatch.setattr(g, "_GROQ_API_KEY", "x")
    monkeypatch.setattr(g, "_groq_client", lambda: _Client())
    out = g.gerar_narrativa("CRIA", 0.5, 100, 1000.0, 500.0, None)
    assert out == "texto"
    assert "sem solicitação de crédito" in capturado["messages"][0]["content"]
