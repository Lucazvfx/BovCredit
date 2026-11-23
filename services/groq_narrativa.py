"""Geração de narrativa e chat de crédito via Groq (Llama 3.3 70B, gratuito).

Feature flag: ativo apenas quando GROQ_API_KEY está definido no ambiente.
Para desativar sem alterar código: remova a variável de ambiente no Railway.
Para reverter completamente: delete este arquivo e remova as linhas de import em app.py.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
_MODEL = 'llama-3.3-70b-versatile'
_TIMEOUT = 20  # segundos


def _feature_ativa() -> bool:
    return bool(_GROQ_API_KEY)


def _groq_client():
    try:
        from groq import Groq
        return Groq(api_key=_GROQ_API_KEY)
    except ImportError:
        logger.warning('groq não instalado — narrativa desativada (pip install groq)')
        return None


_CAMPOS_TEXTO = {'fazenda': 120, 'municipio': 80, 'proprietario': 120, 'recomendacao': 40}
_LIMITE_VALOR = 1e13


class ContextoInvalido(ValueError):
    """Payload de narrativa inválido; a mensagem é fixa e segura para o cliente."""


def _numero(valor, campo, minimo=None, maximo=None):
    """Converte para float finito. None/'' → None; bool, NaN/inf, texto não numérico → ValueError."""
    if valor is None or valor == '':
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
        raise ContextoInvalido(f"Campo '{campo}' deve ser numérico.")
    try:
        n = float(valor)
    except (ValueError, OverflowError):
        raise ContextoInvalido(f"Campo '{campo}' deve ser numérico.") from None
    if n != n or abs(n) > _LIMITE_VALOR:
        raise ContextoInvalido(f"Campo '{campo}' fora do intervalo válido.")
    if (minimo is not None and n < minimo) or (maximo is not None and n > maximo):
        raise ContextoInvalido(f"Campo '{campo}' fora do intervalo válido.")
    return n


def normalizar_confianca(valor) -> Optional[float]:
    """
    Devolve a confiança como fração 0–1, ou None se ausente.
    O contrato é fração; 0–100 é aceito por compatibilidade (valores > 1 são
    percentuais, então 1 vale 100%).
    """
    n = _numero(valor, 'confianca', 0, 100)
    if n is None:
        return None
    return n / 100 if n > 1 else n


def sanitizar_contexto(ctx: dict) -> dict:
    """
    Valida e normaliza o contexto recebido em /api/narrativa.
    Levanta ValueError (mensagem segura para o cliente) em tipo/valor inválido;
    None/ausente recebem fallback seguro. Só devolve chaves aceitas por gerar_narrativa.
    """
    tipo = ctx.get('tipo')
    if not isinstance(tipo, str) or not tipo.strip() or len(tipo) > 40:
        raise ContextoInvalido("Campo 'tipo' inválido.")
    out = {'tipo': tipo.strip()}
    out['confianca'] = normalizar_confianca(ctx.get('confianca'))  # None se ausente
    out['total_rebanho'] = int(_numero(ctx.get('total_rebanho'), 'total_rebanho', 0) or 0)
    out['receita_anual'] = _numero(ctx.get('receita_anual'), 'receita_anual') or 0.0
    out['geracao_caixa_anual'] = _numero(ctx.get('geracao_caixa_anual'), 'geracao_caixa_anual') or 0.0
    out['dscr'] = _numero(ctx.get('dscr'), 'dscr')
    out['limite_credito'] = _numero(ctx.get('limite_credito'), 'limite_credito', 0)
    out['coe_por_arroba'] = _numero(ctx.get('coe_por_arroba'), 'coe_por_arroba', 0)
    score = _numero(ctx.get('consistencia_score'), 'consistencia_score', 0, 100)
    out['consistencia_score'] = 100 if score is None else int(score)
    for campo, limite in _CAMPOS_TEXTO.items():
        v = ctx.get(campo)
        if v is None:
            out[campo] = None if campo == 'recomendacao' else ''
        elif isinstance(v, str):
            out[campo] = v.strip()[:limite]
        else:
            raise ContextoInvalido(f"Campo '{campo}' deve ser texto.")
    return out


def _conf_str(valor) -> str:
    """Confiança formatada em %, sem nunca lançar (o chat passa contexto do cliente)."""
    try:
        c = normalizar_confianca(valor)
    except (ValueError, OverflowError):
        c = None
    return 'não informada' if c is None else f"{c:.0%}"


def _contexto_str(d: dict) -> str:
    """Serializa o contexto do parecer em texto legível para o prompt."""
    tipo = d.get('tipo', 'CICLO_COMPLETO')
    ciclo_desc = {
        'CRIA': 'ciclo de cria (produção de bezerros)',
        'RECRIA': 'ciclo de recria (engorda de garrotes)',
        'ENGORDA': 'ciclo de engorda/terminação',
        'CICLO_COMPLETO': 'ciclo completo (cria, recria e engorda integrados)',
        'RECRIA_ENGORDA': 'recria/engorda (compra de magro e terminação, giro alto)',
        'CRIA_RECRIA': 'sistema misto cria+recria (produção própria e compra de desmama)',
    }.get(tipo, tipo)
    # recomendacao é None quando não há solicitação de crédito (chave presente, valor nulo).
    _rec = d.get('recomendacao')
    rec_str = {
        'aprovar': 'APROVADO',
        'ressalva': 'APROVADO COM RESSALVAS',
        'negar': 'NEGADO',
    }.get(_rec) or (str(_rec).upper() if _rec else 'NÃO AVALIADO (sem solicitação de crédito)')

    partes = [
        f"Fazenda: {d.get('fazenda') or 'não informada'}" + (f" — {d['municipio']}" if d.get('municipio') else ""),
        f"Proprietário: {d['proprietario']}" if d.get('proprietario') else None,
        f"Ciclo detectado: {ciclo_desc} (confiança ML: {_conf_str(d.get('confianca'))})",
        f"Rebanho total: {d.get('total_rebanho', 0):,.0f} cabeças",
        f"Receita anual projetada: R$ {d.get('receita_anual', 0):,.0f}",
        f"Geração de caixa: R$ {d.get('geracao_caixa_anual', 0):,.0f}/ano",
        f"DSCR (índice de cobertura da dívida): {d['dscr']:.2f}" if d.get('dscr') else "DSCR: não calculado",
        f"COE (custo operacional efetivo): R$ {d['coe_por_arroba']:.2f}/@" if d.get('coe_por_arroba') else None,
        f"Score de consistência do rebanho: {d.get('consistencia_score', 100)}/100",
        f"Parecer final: {rec_str}",
        f"Limite de crédito sugerido: R$ {d['limite_credito']:,.0f}" if d.get('limite_credito') else None,
    ]
    return '\n'.join(p for p in partes if p)


def gerar_narrativa(
    tipo: str,
    confianca: float,
    total_rebanho: int,
    receita_anual: float,
    geracao_caixa_anual: float,
    recomendacao: str,
    dscr: Optional[float] = None,
    limite_credito: Optional[float] = None,
    coe_por_arroba: Optional[float] = None,
    consistencia_score: int = 100,
    fazenda: str = '',
    municipio: str = '',
    proprietario: str = '',
) -> Optional[str]:
    """
    Gera narrativa de crédito com Groq. Retorna None se feature inativa ou falhar.
    Nunca lança exceção — não bloqueia o fluxo principal.
    """
    if not _feature_ativa():
        return None

    client = _groq_client()
    if client is None:
        return None

    contexto = _contexto_str({
        'tipo': tipo, 'confianca': confianca, 'total_rebanho': total_rebanho,
        'receita_anual': receita_anual, 'geracao_caixa_anual': geracao_caixa_anual,
        'dscr': dscr, 'recomendacao': recomendacao, 'limite_credito': limite_credito,
        'coe_por_arroba': coe_por_arroba, 'consistencia_score': consistencia_score,
        'fazenda': fazenda, 'municipio': municipio, 'proprietario': proprietario,
    })

    prompt = (
        "Você é um analista sênior de crédito rural especializado em pecuária de corte.\n"
        "Com base nos dados abaixo, escreva um parecer analítico em português, claro e objetivo, "
        "com 3 a 4 parágrafos curtos. Mencione o ciclo produtivo detectado, os pontos fortes, "
        "os principais riscos e a recomendação final. Tom: profissional e direto. Sem bullet points.\n\n"
        f"Dados da análise:\n{contexto}"
    )

    try:
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=600,
            temperature=0.4,
            timeout=_TIMEOUT,
        )
        texto = resp.choices[0].message.content.strip()
        return texto if texto else None
    except Exception as e:
        logger.warning(f'Groq narrativa falhou (não crítico): {e}')
        return None


def gerar_resposta_chat(
    mensagem: str,
    historico: list,
    contexto: dict,
) -> Optional[str]:
    """
    Responde perguntas sobre o parecer via chat.
    historico: lista de {'role': 'user'|'assistant', 'content': str} (últimas N trocas).
    contexto: dict com os dados do parecer (mesmo formato de _contexto_str).
    Retorna None se feature inativa ou falhar.
    """
    if not _feature_ativa():
        return None

    client = _groq_client()
    if client is None:
        return None

    ctx_str = _contexto_str(contexto)
    system_prompt = (
        "Você é um analista sênior de crédito rural especializado em pecuária de corte, "
        "assistindo um usuário da Orkavyn Agro Intelligence.\n\n"
        f"Contexto do parecer atual:\n{ctx_str}\n\n"
        "Responda em português, de forma direta e profissional. "
        "Máximo 3 parágrafos curtos. Sem bullet points. "
        "Se a pergunta não tiver relação com o parecer ou com crédito/pecuária rural, "
        "informe educadamente que só pode ajudar com esse tema."
    )

    messages = [{'role': 'system', 'content': system_prompt}]
    for h in historico[-8:]:  # mantém até 8 turnos de histórico
        role = h.get('role', 'user')
        content = h.get('content', '')
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content})
    messages.append({'role': 'user', 'content': mensagem})

    try:
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            max_tokens=450,
            temperature=0.3,
            timeout=_TIMEOUT,
        )
        texto = resp.choices[0].message.content.strip()
        return texto if texto else None
    except Exception as e:
        logger.warning(f'Groq chat falhou (não crítico): {e}')
        return None
