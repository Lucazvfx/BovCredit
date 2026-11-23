"""Exportação CSV da carteira de propostas comerciais.

Só texto e formatação: nenhuma regra financeira aqui. O que entra na planilha
é uma lista fechada de colunas — referência, valores, enquadramento e decisor.
Sem e-mail, sem criador, sem o texto livre do parecer do aprovador.
"""
import csv
import io

from services.papeis_empresa import PROPOSTA_ROTULO
from services.politica_alcada import ROTULOS_STATUS

CABECALHO = (
    'Data de registro', 'Referência', 'Parecer vinculado', 'Valor pretendido (R$)',
    'Prazo (meses)', 'Enquadramento de alçada', 'Situação', 'Decisor',
    'Data da decisão',
)

# Planilhas executam como fórmula a célula que começa com estes caracteres
# (inclusive depois de espaço, tab ou quebra de linha).
_GATILHOS = ('=', '+', '-', '@')


def neutralizar_celula(valor) -> str:
    """Texto seguro para planilha: prefixa `'` quando poderia virar fórmula."""
    texto = '' if valor is None else str(valor)
    if texto[:1] in ('\t', '\r', '\n') or texto.lstrip()[:1] in _GATILHOS:
        return "'" + texto
    return texto


def _data(valor, tamanho=16) -> str:
    return str(valor or '')[:tamanho]


def propostas_para_csv(propostas: list) -> str:
    """CSV (`;`, UTF-8 com BOM) para o Excel em pt-BR abrir sem ajuste."""
    saida = io.StringIO()
    saida.write('\ufeff')  # BOM: o Excel reconhece UTF-8
    w = csv.writer(saida, delimiter=';', lineterminator='\r\n')
    w.writerow(CABECALHO)
    for p in propostas:
        w.writerow([
            _data(p.get('criado_em')),
            neutralizar_celula(p.get('referencia')),
            p['parecer_id'] if p.get('parecer_id') else '',
            f"{float(p['valor_pretendido']):.2f}".replace('.', ','),
            int(p['prazo_meses']),
            neutralizar_celula(ROTULOS_STATUS.get(p['status_alcada'], p['status_alcada'])),
            neutralizar_celula(PROPOSTA_ROTULO.get(p['status'], p['status'])),
            neutralizar_celula(p.get('decidido_por_nome')),
            _data(p.get('decidido_em')),
        ])
    return saida.getvalue()
