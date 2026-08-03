"""
O limitador de força bruta estava se voltando contra os usuários.

Achado na checagem de pré-lançamento, não no código: `@limiter.limit("10 per
minute; 30 per hour")` no view de `/login` contava TODOS os métodos — inclusive
o GET, ou seja o simples ato de ABRIR A TELA DE LOGIN.

Medido num app recém-iniciado: do décimo acesso em diante a página respondia
429 e ninguém mais entrava. Força bruta é POST; GET de página de login não é
tentativa de nada.

O segundo defeito é o que transformava isso em queda geral. Em produção o app
roda atrás do proxy do Railway e `get_remote_address` lê `remote_addr`, que sem
`ProxyFix` é o IP DO PROXY — todos os clientes da plataforma no mesmo balde.
Dez aberturas de tela por minuto SOMADAS entre todas as consultorias
derrubariam o login de todas ao mesmo tempo.

Os dois juntos são queda de plataforma no dia do lançamento, por um mecanismo
que existe para proteger.
"""
import pytest

import database as db
from app import app, limiter


@pytest.fixture
def cli():
    db.init_db()
    app.config['TESTING'] = True
    # O limitador é desligado sob TESTING por padrão em várias suítes; aqui ele
    # é o objeto do teste, então fica explicitamente ligado.
    limiter.enabled = True
    limiter.reset()
    c = app.test_client()
    yield c
    limiter.reset()
    limiter.enabled = True


def test_abrir_a_tela_de_login_nao_consome_cota(cli):
    """
    Vinte aberturas seguidas. Um analista que recarrega a página, dois que
    chegam juntos às oito da manhã, ou um monitor de uptime pingando /login
    não podem trancar a plataforma.
    """
    for i in range(20):
        r = cli.get('/login')
        assert r.status_code == 200, (
            f'a {i + 1}ª abertura da tela de login devolveu {r.status_code} — '
            f'o limitador voltou a contar GET'
        )


def test_a_forca_bruta_continua_bloqueada(cli):
    """
    Contrapeso: soltar o GET não pode ter soltado o POST. O limite é de 10 por
    minuto, então a 11ª tentativa de senha tem de ser recusada.
    """
    codigos = [cli.post('/login', data={'email': 'nao@existe.com',
                                        'password': 'errada'}).status_code
               for _ in range(15)]
    assert 429 in codigos, 'a força bruta deixou de ser bloqueada'
    assert codigos.index(429) >= 10, (
        f'bloqueou na tentativa {codigos.index(429) + 1} — antes do limite de 10'
    )


def test_o_limitador_enxerga_o_cliente_e_nao_o_proxy():
    """
    Sem ProxyFix, `remote_addr` é o IP do proxy do Railway e todos os clientes
    compartilham o mesmo balde. Com ele, dois clientes atrás do mesmo proxy têm
    cotas independentes.

    `x_for=1` confia em UM salto: o do proxy imediatamente à frente. Confiar em
    mais deixaria um cliente forjar o cabeçalho e escolher um IP a cada
    tentativa, escapando do limite.
    """
    from werkzeug.middleware.proxy_fix import ProxyFix
    assert isinstance(app.wsgi_app, ProxyFix), (
        'ProxyFix saiu — o limitador voltou a ver o IP do proxy e todos os '
        'usuários da plataforma compartilham a mesma cota'
    )
    assert app.wsgi_app.x_for == 1, (
        f'x_for={app.wsgi_app.x_for} — confiar em mais de um salto permite '
        f'forjar X-Forwarded-For e escapar do limitador'
    )


def test_clientes_diferentes_tem_cotas_independentes(cli):
    """
    O efeito prático do ProxyFix: esgotar a cota de um IP não pode trancar
    outro. É a diferença entre bloquear um atacante e bloquear a plataforma.
    """
    def tenta(ip):
        return cli.post('/login',
                        data={'email': 'nao@existe.com', 'password': 'errada'},
                        headers={'X-Forwarded-For': ip}).status_code

    codigos_a = [tenta('203.0.113.10') for _ in range(15)]
    assert 429 in codigos_a, 'o primeiro cliente não foi bloqueado'

    # Outro cliente, atrás do mesmo proxy, continua entrando.
    assert tenta('198.51.100.20') != 429, (
        'bloquear um cliente bloqueou o outro — os dois estão no mesmo balde'
    )
