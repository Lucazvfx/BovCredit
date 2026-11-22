"""ZARC — Zoneamento Agrícola de Risco Climático na análise de grãos.

Os casos de Sorriso/MT usam a tábua oficial versionada em data/zarc/2026-2027
(Port. 202/2026 para soja, Port. 326/2026 para milho 2ª safra):

    soja, solo AD3, Grupo II, sequeiro .... 20% de 01/10 a 10/01, fora no resto
    milho 2ª safra, AD3, Grupo II ......... 20% em janeiro, 40% em 01–10/02
"""
from datetime import date

import pytest

from services.annual_engine import analisar_culturas_anuais
from services.zarc import avaliar_zarc, decendio

SORRISO = {'municipio': 'Sorriso', 'uf': 'MT', 'cod_solo': 13}


def _cultura(nome, safra_tipo, plantio, ciclo=21):
    return {'cultura': nome, 'safra_tipo': safra_tipo,
            'zarc': {'data_plantio': plantio, 'cod_ciclo': ciclo}}


def _uma(resultado):
    return resultado['culturas'][0]


@pytest.mark.parametrize('dia,esperado', [
    (date(2027, 1, 1), 1), (date(2027, 1, 10), 1), (date(2027, 1, 11), 2),
    (date(2027, 1, 31), 3), (date(2026, 10, 1), 28), (date(2026, 12, 15), 35),
    (date(2026, 12, 31), 36),
])
def test_decendio_do_ano(dia, esperado):
    assert decendio(dia) == esperado


def test_soja_dentro_do_zoneamento():
    r = _uma(avaliar_zarc(SORRISO, [_cultura('SOJA', '1_SAFRA', '2026-10-15')], '2026/27'))
    assert r['status'] == 'dentro'
    assert r['risco_pct'] == 20
    assert r['decendio'] == 29
    assert r['portaria'].startswith('Port.202')


def test_soja_fora_do_zoneamento_mostra_a_melhor_janela():
    r = _uma(avaliar_zarc(SORRISO, [_cultura('SOJA', '1_SAFRA', '2027-02-15')], '2026/27'))
    assert r['status'] == 'fora'
    assert r['risco_pct'] is None
    # A janela atravessa a virada do ano: dec28 (01/10) até dec1 (10/01).
    assert r['melhor_janela'] == {'risco_pct': 20, 'inicio': '01/10', 'fim': '10/01'}


def test_milho_safrinha_com_risco_alto():
    r = _uma(avaliar_zarc(SORRISO, [_cultura('MILHO', '2_SAFRA', '2027-02-05')], '2026/27'))
    assert r['cultura_zarc'] == 'Milho 2ª Safra'
    assert r['status'] == 'dentro'
    assert r['risco_pct'] == 40
    assert r['melhor_janela'] == {'risco_pct': 20, 'inicio': '01/01', 'fim': '31/01'}


def test_municipio_aceita_caixa_e_acento_diferentes():
    zarc = {'municipio': "alta floresta d oeste", 'uf': 'ro', 'cod_solo': 13}
    resultado = avaliar_zarc(zarc, [_cultura('SOJA', '1_SAFRA', '2026-10-15')], '2026/27')
    assert resultado['geocodigo'] == '1100015'
    assert resultado['municipio'] == "Alta Floresta D'Oeste"


def test_municipio_desconhecido_nao_avalia():
    zarc = {'municipio': 'Cidade Que Não Existe', 'uf': 'MT', 'cod_solo': 13}
    r = _uma(avaliar_zarc(zarc, [_cultura('SOJA', '1_SAFRA', '2026-10-15')], '2026/27'))
    assert r['status'] == 'nao_avaliado'
    assert 'não encontrado' in r['motivo']


def test_cultura_sem_zarc_no_orkavyn_nao_avalia():
    r = _uma(avaliar_zarc(SORRISO, [_cultura('CAFÉ', '1_SAFRA', '2026-10-15')], '2026/27'))
    assert r['status'] == 'nao_avaliado'
    assert 'cultura' in r['motivo']


def test_combinacao_sem_zoneamento_nao_avalia():
    # Solo "Arenoso" (1) não existe para soja, que usa as classes AD1–AD6.
    zarc = dict(SORRISO, cod_solo=1)
    r = _uma(avaliar_zarc(zarc, [_cultura('SOJA', '1_SAFRA', '2026-10-15')], '2026/27'))
    assert r['status'] == 'nao_avaliado'
    assert 'solo' in r['motivo']


def test_sem_data_de_plantio_so_indica_a_janela():
    r = _uma(avaliar_zarc(SORRISO, [_cultura('SOJA', '1_SAFRA', '')], '2026/27'))
    assert r['status'] == 'nao_avaliado'
    assert r['melhor_janela']['inicio'] == '01/10'


def test_safra_sem_tabua_carregada_nao_avalia():
    r = _uma(avaliar_zarc(SORRISO, [_cultura('SOJA', '1_SAFRA', '2019-10-15')], '2019/20'))
    assert r['status'] == 'nao_avaliado'
    assert '2019/2020' in r['motivo']


def _payload_graos(plantio_soja):
    return {
        'ano_agricola': '2026/27',
        'zarc': SORRISO,
        'culturas': [{
            'cultura': 'SOJA', 'safra_tipo': '1_SAFRA', 'area_ha': 800,
            'produtividade_ha': 60, 'preco_unitario': 144, 'coe_ha': 4100,
            'zarc': {'data_plantio': plantio_soja, 'cod_ciclo': 21},
        }],
        'credito': {'valor': 800_000, 'prazo_meses': 36, 'juros_aa': 0.115},
    }


def test_analise_de_graos_traz_o_zarc_e_avisa_quando_fora():
    analise = analisar_culturas_anuais(_payload_graos('2027-02-15'))
    assert analise['zarc']['culturas'][0]['status'] == 'fora'
    assert any('ZARC' in a and 'Proagro' in a for a in analise['avisos'])


def test_analise_de_graos_sem_zarc_segue_igual():
    payload = _payload_graos('2026-10-15')
    del payload['zarc']
    analise = analisar_culturas_anuais(payload)
    assert analise['zarc'] is None
    assert not any('ZARC' in a for a in analise['avisos'])


def test_pdf_do_parecer_tem_a_secao_zarc():
    import io
    import pdfplumber
    from services.parecer_pdf_graos import gerar_pdf_parecer_graos

    analise = analisar_culturas_anuais(_payload_graos('2027-02-15'))
    pdf = gerar_pdf_parecer_graos(analise, identificacao={'fazenda': 'Fazenda Verde'})
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        texto = '\n'.join(p.extract_text() or '' for p in doc.pages)
    assert 'Risco Climático (ZARC)' in texto
    assert 'Fora do zoneamento' in texto
    assert 'Port.202' in texto


def test_endpoint_de_graos_devolve_o_zarc():
    import database as db
    db.init_db()
    email = 'zarctest@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'Usuario ZARC', 'senha123')
        usuario = db.buscar_usuario_email(email)
    from app import app
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])

    resp = cliente.post('/api/agricola/graos/analisar', json=_payload_graos('2026-10-15'))
    assert resp.status_code == 200
    soja = resp.get_json()['zarc']['culturas'][0]
    assert soja['status'] == 'dentro'
    assert soja['risco_pct'] == 20
