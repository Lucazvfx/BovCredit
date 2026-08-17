"""services/situacao_cadastral.py — CNPJ via BrasilAPI, CPF sempre recusado.

Este ambiente bloqueia rede para hosts fora da lista permitida; todas as
chamadas HTTP são mockadas via monkeypatch (mesma convenção de
test_ibge_sidra.py). A primeira execução contra a BrasilAPI real é a
validação de verdade.
"""
import requests

from services.situacao_cadastral import (
    consultar, consultar_cnpj, consultar_cpf, validar_cnpj, validar_cpf,
)

CNPJ_VALIDO = '12345678000195'
CPF_VALIDO = '12345678909'


# ── Checksum ─────────────────────────────────────────────────────────────────
def test_valida_cnpj_correto():
    assert validar_cnpj(CNPJ_VALIDO) is True


def test_rejeita_cnpj_com_digito_verificador_errado():
    errado = CNPJ_VALIDO[:-1] + str((int(CNPJ_VALIDO[-1]) + 1) % 10)
    assert validar_cnpj(errado) is False


def test_rejeita_cnpj_com_todos_digitos_iguais():
    assert validar_cnpj('11111111111111') is False


def test_rejeita_cnpj_com_tamanho_errado():
    assert validar_cnpj('123') is False


def test_valida_cpf_correto():
    assert validar_cpf(CPF_VALIDO) is True


def test_rejeita_cpf_com_digito_verificador_errado():
    errado = CPF_VALIDO[:-1] + str((int(CPF_VALIDO[-1]) + 1) % 10)
    assert validar_cpf(errado) is False


# ── CPF: nunca tenta consultar ───────────────────────────────────────────────
def test_cpf_nunca_dispara_chamada_de_rede(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError('CPF não deveria disparar chamada de rede')
    monkeypatch.setattr(requests, 'get', _explode)

    r = consultar_cpf(CPF_VALIDO)

    assert r['disponivel'] is False
    assert 'Serasa' in r['motivo'] or 'bureau' in r['motivo']


def test_consultar_roteia_cpf_pelo_tamanho(monkeypatch):
    monkeypatch.setattr(requests, 'get',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('não deveria chamar')))
    r = consultar(CPF_VALIDO)
    assert r['tipo'] == 'CPF'
    assert r['disponivel'] is False


# ── CNPJ: os três estados ────────────────────────────────────────────────────
class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_cnpj_ativo(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(200, {
        'descricao_situacao_cadastral': 'ATIVA',
        'data_situacao_cadastral': '2015-03-10',
        'razao_social': 'FAZENDA TESTE LTDA',
        'municipio': 'CUIABA', 'uf': 'MT',
    }))

    r = consultar_cnpj(CNPJ_VALIDO)

    assert r['encontrado'] is True
    assert r['situacao'] == 'ATIVA'
    assert r['regular'] is True
    assert r['razao_social'] == 'FAZENDA TESTE LTDA'
    assert r['fonte'] == 'Receita Federal (via BrasilAPI)'


def test_cnpj_baixada_nao_e_regular(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(200, {
        'descricao_situacao_cadastral': 'BAIXADA',
        'motivo_situacao_cadastral': 'EXTINCAO',
    }))

    r = consultar_cnpj(CNPJ_VALIDO)

    assert r['encontrado'] is True
    assert r['situacao'] == 'BAIXADA'
    assert r['regular'] is False


def test_cnpj_nao_encontrado(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(404))

    r = consultar_cnpj(CNPJ_VALIDO)

    assert r['encontrado'] is False
    assert 'erro' in r


def test_cnpj_invalido_nao_dispara_rede(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError('CNPJ inválido não deveria disparar chamada de rede')
    monkeypatch.setattr(requests, 'get', _explode)

    r = consultar_cnpj('12345678000199')  # dígito verificador errado

    assert r['encontrado'] is False
    assert 'inválido' in r['erro']


def test_falha_de_rede_devolve_none_nao_false(monkeypatch):
    """None = "não sei" — jamais pode virar "não existe" nem "regular"."""
    def _explode(*a, **k):
        raise requests.ConnectionError('timeout')
    monkeypatch.setattr(requests, 'get', _explode)

    r = consultar_cnpj(CNPJ_VALIDO)

    assert r['encontrado'] is None
    assert 'erro' in r


def test_servico_fora_do_ar_devolve_none(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(503))

    r = consultar_cnpj(CNPJ_VALIDO)

    assert r['encontrado'] is None


def test_resposta_em_formato_inesperado_nao_levanta(monkeypatch):
    class _RespQuebrada:
        status_code = 200
        def json(self):
            raise ValueError('not json')
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _RespQuebrada())

    r = consultar_cnpj(CNPJ_VALIDO)

    assert r['encontrado'] is None
    assert 'erro' in r


def test_consultar_roteia_cnpj_pelo_tamanho(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(200, {
        'descricao_situacao_cadastral': 'ATIVA'}))
    r = consultar(CNPJ_VALIDO)
    assert r['tipo'] == 'CNPJ'


def test_documento_com_tamanho_invalido():
    r = consultar('123')
    assert r['tipo'] is None
    assert r['encontrado'] is False


def test_aceita_documento_formatado_com_pontuacao(monkeypatch):
    """12.345.678/0001-95 tem que funcionar igual a 12345678000195."""
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(200, {
        'descricao_situacao_cadastral': 'ATIVA'}))
    formatado = '12.345.678/0001-95'
    r = consultar_cnpj(formatado)
    assert r['documento'] == CNPJ_VALIDO
    assert r['encontrado'] is True
