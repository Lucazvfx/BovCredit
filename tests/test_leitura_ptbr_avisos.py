"""Regressão: leitura de PDF não pode errar nem calar em silêncio.

Achados da auditoria de parsers: `parsear_generico` lia "1.250" como 250
(rebanho 5x menor, sem alerta) e uma linha de animal não reconhecida passava
sem nenhum aviso, mesmo com o TOTAL do documento divergente.
"""
import pytest

from pdf_parsers import avisos_leitura, parsear_generico
from services.fichas_rebanho.base_reader import read_ficha_text


def test_milhar_com_ponto_nao_trunca_quantidade():
    d = parsear_generico(
        'Fêmeas 0 a 12 meses 1.250\nMachos 0 a 12 meses 1.100\n'
        'Fêmeas acima de 36 meses 2.300\n')
    assert d['total'] == 4650


def test_decimal_ptbr_sem_fracao_e_lido_como_inteiro():
    d = parsear_generico(
        'Fêmeas 13 a 24 meses 250,00\nMachos 13 a 24 meses 800,00\n')
    assert d['total'] == 1050


def test_quantidade_sem_milhar_continua_igual():
    d = parsear_generico('Fêmeas 13 a 24 meses 250\nMachos 13 a 24 meses 800\n')
    assert d['total'] == 1050


def test_linha_nao_reconhecida_gera_aviso_de_total_divergente():
    texto = (
        'Fêmeas 0 a 12 meses 100\nMachos 0 a 12 meses 100\n'
        'Bubalinos femeas 500\nTOTAL 700\n')
    leitura = read_ficha_text(texto)
    assert leitura['sucesso'] is True
    assert any('700' in a and '200' in a for a in leitura['avisos'])


def test_total_conferido_nao_gera_aviso():
    texto = (
        'Fêmeas 0 a 12 meses 100\nMachos 0 a 12 meses 100\nTOTAL 200\n')
    assert read_ficha_text(texto)['avisos'] == []


def test_total_do_documento_com_milhar_e_comparado_corretamente():
    texto = 'Fêmeas 0 a 12 meses 1.000\nMachos 0 a 12 meses 500\nTOTAL 1.500\n'
    assert avisos_leitura(texto, parsear_generico(texto)) == []


@pytest.mark.parametrize('texto', ['', '   \n  '])
def test_pdf_sem_texto_avisa_possivel_escaneado(texto):
    avisos = avisos_leitura(texto, {'total': 0})
    assert avisos and 'sem texto' in avisos[0]


def test_rebanho_zerado_avisa():
    texto = 'Fêmeas 0 a 12 meses 0\nMachos 0 a 12 meses 0\n'
    avisos = avisos_leitura(texto, parsear_generico(texto))
    assert avisos and 'Nenhuma categoria' in avisos[0]


def test_entrada_forjada_com_milhar_gigante_nao_levanta():
    parsear_generico('Femeas 0 a 12 meses 1' + '.000' * 1500)
    avisos_leitura('Femeas 0 a 12 meses 10\nTOTAL ' + '9' * 5000, {'total': 10})


def test_milhar_en_us_nao_vira_quantidade_menor():
    assert parsear_generico('Femeas 0 a 12 meses 3,000')['total'] == 0
