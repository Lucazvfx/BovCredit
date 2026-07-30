"""Geração de narrativa de crédito via Groq (Llama 3.3 70B, gratuito).

Feature flag: ativo apenas quando GROQ_API_KEY está definido no ambiente.
Para desativar sem alterar código: remova a variável de ambiente no Railway.
Para reverter completamente: delete este arquivo e remova a linha de chamada em app.py.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
_MODEL = 'llama-3.3-70b-versatile'
_TIMEOUT = 15  # segundos


def _feature_ativa() -> bool:
    return bool(_GROQ_API_KEY)


def _montar_prompt(d: dict) -> str:
    tipo = d.get('tipo', 'CICLO_COMPLETO')
    conf = d.get('confianca', 0)
    total = d.get('total_rebanho', 0)
    receita = d.get('receita_anual', 0)
    dscr = d.get('dscr')
    rec = d.get('recomendacao', 'ressalva')
    limite = d.get('limite_credito', 0)
    fazenda = d.get('fazenda', 'não informada')
    municipio = d.get('municipio', '')
    proprietario = d.get('proprietario', '')
    consistencia_score = d.get('consistencia_score', 100)
    coe = d.get('coe_por_arroba')
    gc = d.get('geracao_caixa_anual', 0)

    ciclo_desc = {
        'CRIA': 'ciclo de cria (foco em produção de bezerros)',
        'RECRIA': 'ciclo de recria (engorda de garrotes)',
        'ENGORDA': 'ciclo de engorda/terminação',
        'CICLO_COMPLETO': 'ciclo completo (cria, recria e engorda integrados)',
    }.get(tipo, tipo)

    rec_str = {
        'aprovar': 'APROVADO',
        'ressalva': 'APROVADO COM RESSALVAS',
        'negar': 'NEGADO',
    }.get(rec, rec.upper())

    partes = [
        f"Fazenda: {fazenda}" + (f" — {municipio}" if municipio else ""),
        f"Proprietário: {proprietario}" if proprietario else None,
        f"Ciclo detectado: {ciclo_desc} (confiança ML: {conf:.0%})",
        f"Rebanho: {total:,.0f} cabeças",
        f"Receita anual projetada: R$ {receita:,.0f}",
        f"Geração de caixa: R$ {gc:,.0f}/ano",
        f"DSCR: {dscr:.2f}" if dscr else "DSCR: não calculado",
        f"COE: R$ {coe:.2f}/@ " if coe else None,
        f"Score de consistência do rebanho: {consistencia_score}/100",
        f"Parecer: {rec_str}",
        f"Limite sugerido: R$ {limite:,.0f}" if limite else None,
    ]
    contexto = '\n'.join(p for p in partes if p)

    return f"""Você é um analista sênior de crédito rural especializado em pecuária de corte.
Com base nos dados abaixo, escreva um parecer analítico em português, claro e objetivo,
com 3 a 4 parágrafos curtos. Mencione o ciclo produtivo detectado, os pontos fortes,
os principais riscos e a recomendação final. Tom: profissional e direto. Sem bullet points.

Dados da análise:
{contexto}
"""


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
    Nunca lança exceção para não quebrar o fluxo principal.
    """
    if not _feature_ativa():
        return None

    try:
        from groq import Groq  # importação tardia para não bloquear o boot se não instalado
    except ImportError:
        logger.warning('groq não instalado — narrativa desativada (pip install groq)')
        return None

    prompt = _montar_prompt({
        'tipo': tipo,
        'confianca': confianca,
        'total_rebanho': total_rebanho,
        'receita_anual': receita_anual,
        'geracao_caixa_anual': geracao_caixa_anual,
        'dscr': dscr,
        'recomendacao': recomendacao,
        'limite_credito': limite_credito,
        'coe_por_arroba': coe_por_arroba,
        'consistencia_score': consistencia_score,
        'fazenda': fazenda,
        'municipio': municipio,
        'proprietario': proprietario,
    })

    try:
        client = Groq(api_key=_GROQ_API_KEY)
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
