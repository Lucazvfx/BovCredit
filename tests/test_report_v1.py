import io

import pdfplumber

import database
from app import app
from services.parecer_pdf import gerar_pdf_parecer


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as document:
        return "\n".join(page.extract_text() or "" for page in document.pages)


def _sample_parecer() -> dict:
    return {
        "identificacao": {"fazenda": "Fazenda Teste", "municipio": "Juara - MT"},
        "composicao": {"total": 200},
        "indicadores": {"total_femeas": 120, "total_machos": 80},
        "fluxo_gep": {
            "receita_vendas": 720_000,
            "custo_operacional": 390_000,
            "resultado_operacional": 330_000,
        },
        "conclusao": {"recomendacao": "ressalva", "dscr_minimo": 1.11},
        "qualidade_dados": {"status": "COMPLETO"},
    }


def test_demo_is_visibly_fictitious():
    client = app.test_client()

    response = client.get("/demo")

    assert response.status_code == 200
    content = response.get_data(as_text=True).upper()
    assert "DEMONSTRA" in content
    assert "FICT" in content


def test_report_snapshot_requires_login():
    client = app.test_client()

    response = client.get("/api/report/1")

    assert response.status_code in (302, 401)


def test_pdf_contains_b2b_section_titles():
    text = _extract_pdf_text(gerar_pdf_parecer(_sample_parecer()))

    assert "Resumo executivo" in text
    assert "Qualidade dos dados" in text
    assert "Limitações" in text


def test_pdf_b2b_sections_follow_review_order():
    text = _extract_pdf_text(gerar_pdf_parecer(_sample_parecer()))
    lines = [line.strip() for line in text.splitlines()]
    sections = (
        "Resumo executivo",
        "Rebanho",
        "Produção",
        "Receitas",
        "Custos",
        "Fluxo de caixa",
        "Dívida",
        "DSCR",
        "Stress",
        "Risco",
        "Qualidade dos dados",
        "Premissas",
        "Fontes",
        "Limitações",
    )

    positions = [lines.index(section) for section in sections]
    assert positions == sorted(positions)


def test_demo_does_not_persist_analysis(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("a demonstração pública não pode persistir análise")

    monkeypatch.setattr(database, "save_analysis_snapshot", fail_if_called)

    response = app.test_client().get("/demo")

    assert response.status_code == 200


def test_demo_uses_shared_fields_visual_system():
    response = app.test_client().get("/demo")
    html = response.get_data(as_text=True)

    assert "orkavyn-fields.css" in html
    assert 'class="ork-surface ork-demo"' in html
    assert "DADOS FICTÍCIOS" in html.upper()
