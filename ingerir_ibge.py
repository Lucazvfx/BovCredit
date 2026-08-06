#!/usr/bin/env python3
"""
Job de ingestão do IBGE — tira o "0 medidos" do zero.

    python ingerir_ibge.py                     # busca, calcula e grava
    python ingerir_ibge.py --so-mostrar        # busca e imprime, sem gravar
    python ingerir_ibge.py --periodo 2023      # outro ano

Grava `dados/desfrute_uf.json`, que a camada de proveniência carrega para
transformar o desfrute de `referência` em `medido`.

    ESTE JOB NUNCA RODOU CONTRA A API REAL.

O ambiente de desenvolvimento bloqueia saída para o IBGE (403 no proxy), então
o parsing foi escrito a partir da documentação e testado com fixtures. A
primeira execução com rede é a validação de verdade.

Ela vai falhar alto se o contrato não bater — é assim de propósito. Se
`RespostaInesperada` aparecer, a mensagem traz o payload recebido: compare com
o que `services/ibge_sidra.parse_valores` espera e ajuste os códigos de
variável/classificação abaixo, que são a parte que não pude conferir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

from services import ibge_sidra as sidra

DESTINO = os.path.join(os.path.dirname(__file__), 'dados', 'desfrute_uf.json')

# Códigos de variável e classificação. São a parte NÃO conferida — o número da
# tabela veio do SIDRA, estes vieram de leitura de documentação. Se a primeira
# execução voltar vazia ou com recorte errado, é aqui que se mexe.
VAR_EFETIVO   = '105'       # PPM — efetivo dos rebanhos (cabeças)
CLASS_BOVINO  = 'c79/2670'  # tipo de rebanho = bovino
VAR_ABATE     = '284'       # abate — número de cabeças
CLASS_ABATE   = ''          # total; sem quebra por categoria nesta primeira carga


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--periodo', default='last 1',
                    help="período no formato do SIDRA (default: 'last 1')")
    ap.add_argument('--so-mostrar', action='store_true',
                    help='imprime sem gravar o arquivo')
    args = ap.parse_args()

    print(f'Buscando efetivo (tab. {sidra.TAB_EFETIVO})...')
    efetivo = sidra.baixar(sidra.TAB_EFETIVO, VAR_EFETIVO, args.periodo,
                           classificacao=CLASS_BOVINO)
    print(f'  {len(efetivo)} registro(s)')

    print(f'Buscando abate (tab. {sidra.TAB_ABATE})...')
    abate = sidra.baixar(sidra.TAB_ABATE, VAR_ABATE, args.periodo,
                         classificacao=CLASS_ABATE)
    print(f'  {len(abate)} registro(s)')

    if not efetivo or not abate:
        print('\nUma das séries voltou vazia — sem rede, ou os códigos de '
              'variável/classificação estão errados.\nNada foi gravado.',
              file=sys.stderr)
        return 1

    desfrute = sidra.desfrute_por_uf(efetivo, abate)
    if not desfrute:
        print('\nNenhuma UF casou entre as duas séries. Confira se os recortes '
              'territoriais batem (ambos em n3).', file=sys.stderr)
        return 1

    print(f'\n{"UF":<24}{"EFETIVO":>14}{"ABATE":>14}{"DESFRUTE":>10}')
    for d in sorted(desfrute.values(), key=lambda x: -x['desfrute_pct']):
        print(f'{d["uf"]:<24}{d["efetivo"]:>14,.0f}{d["abate"]:>14,.0f}'
              f'{d["desfrute_pct"]:>9.1f}%')

    if args.so_mostrar:
        print('\n(--so-mostrar: nada gravado)')
        return 0

    saida = {
        'gerado_em': datetime.now().isoformat(timespec='seconds'),
        'periodo':   args.periodo,
        'fonte':     f'IBGE · PPM tab. {sidra.TAB_EFETIVO} ÷ '
                     f'Abate tab. {sidra.TAB_ABATE}',
        'ressalva':  sidra.RESSALVA_DESFRUTE,
        'desfrute_uf': desfrute,
    }
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    with open(DESTINO, 'w', encoding='utf-8') as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print(f'\nGravado em {DESTINO} — {len(desfrute)} UF.')
    print('A camada de proveniência passa a marcar o desfrute como MEDIDO.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
