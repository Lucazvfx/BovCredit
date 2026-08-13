from __future__ import annotations

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _chave_rate_limit() -> str:
    """Chave de rate limiting por user ID quando autenticado, IP como fallback.

    Por quê: em Railway a app roda atrás de load balancer. Sem ProxyFix (já
    aplicado em app.py) get_remote_address devolveria o IP interno do proxy,
    colapsando todos os usuários num único bucket. Com ProxyFix o IP real
    chega corretamente — e para usuários autenticados ainda preferimos o ID
    deles: assim dois analistas do mesmo escritório (mesmo IP público) não
    compartilham cota, e um usuário mal-intencionado não burla o limite
    trocando de IP.

    Para rotas não autenticadas (login, reset de senha) o IP é o identificador
    correto — é exatamente o que queremos bloquear em força bruta.
    """
    try:
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            return f'uid:{current_user.id}'
    except Exception:
        pass
    return get_remote_address()


limiter = Limiter(_chave_rate_limit, default_limits=[])
