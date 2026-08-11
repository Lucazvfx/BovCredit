import io

import pdfplumber

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
