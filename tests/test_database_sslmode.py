"""TLS na conexão PostgreSQL: sslmode=require por padrão em host remoto."""
import pytest

import database

REMOTA = 'postgresql://u:p%40ss@db.exemplo.supabase.co:6543/postgres'


@pytest.fixture(autouse=True)
def _sem_override(monkeypatch):
    monkeypatch.delenv('DATABASE_SSLMODE', raising=False)


def test_host_remoto_sem_sslmode_recebe_require():
    assert database._aplicar_sslmode(REMOTA) == REMOTA + '?sslmode=require'


def test_host_remoto_com_query_existente_acrescenta_com_e_comercial():
    url = REMOTA + '?application_name=orkavyn'
    assert database._aplicar_sslmode(url) == url + '&sslmode=require'


@pytest.mark.parametrize('modo', ['disable', 'prefer', 'verify-full'])
def test_sslmode_explicito_na_url_e_preservado(modo):
    url = f'{REMOTA}?sslmode={modo}'
    assert database._aplicar_sslmode(url) == url


@pytest.mark.parametrize('host', ['localhost', '127.0.0.1', '[::1]'])
def test_host_local_nao_e_alterado(host):
    url = f'postgresql://u:p@{host}:5432/db'
    assert database._aplicar_sslmode(url) == url


def test_url_sem_host_nao_e_alterada():
    assert database._aplicar_sslmode('postgresql:///db') == 'postgresql:///db'


def test_url_vazia_continua_vazia():
    assert database._aplicar_sslmode('') == ''


def test_override_por_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv('DATABASE_SSLMODE', 'disable')
    assert database._aplicar_sslmode(REMOTA) == REMOTA + '?sslmode=disable'


def test_override_invalido_cai_em_require(monkeypatch):
    monkeypatch.setenv('DATABASE_SSLMODE', 'x&y=1')
    assert database._aplicar_sslmode(REMOTA) == REMOTA + '?sslmode=require'


def test_url_na_url_vence_a_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv('DATABASE_SSLMODE', 'disable')
    url = REMOTA + '?sslmode=verify-full'
    assert database._aplicar_sslmode(url) == url


def test_politica_nao_cita_bcrypt_e_cita_operadores():
    from pathlib import Path
    html = (Path(database.__file__).parent / 'templates' / 'privacidade.html').read_text(encoding='utf-8')
    assert 'bcrypt' not in html
    assert 'scrypt' in html and 'sslmode=require' in html
    assert 'Meta (WhatsApp' in html and 'SMTP' in html


def test_ipv6_remoto_e_postgres_scheme_recebem_require():
    assert database._aplicar_sslmode('postgres://u:p@[2001:db8::1]:5432/db').endswith('?sslmode=require')


def test_sslmode_vazio_explicito_e_preservado():
    url = REMOTA + '?sslmode='
    assert database._aplicar_sslmode(url) == url


def test_url_corrompida_do_railway_e_sanitizada_antes_do_sslmode():
    bruta = 'postgresql://a:b@h1.exemplo.com:5432/db${{X}}postgresql://c:d@h2.exemplo.com/db'
    url = database._aplicar_sslmode(database._sanitizar_database_url(bruta))
    assert url.endswith('sslmode=require') and '${' not in url
