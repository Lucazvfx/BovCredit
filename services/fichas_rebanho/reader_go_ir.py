"""Leitor do modelo GO IR baseado na rotina ExtrairDadosGOIR do VBA."""

import re
import unicodedata


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize('NFKD', texto.upper())
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ' '.join(texto.split())


def extrair_blocos(texto: str) -> list[dict]:
    """Extrai inscrição + 8 posições + total, como a macro VBA.

    A macro considera uma inscrição de 8–14 dígitos seguida de nove números
    de até sete dígitos e só aceita o bloco quando o total fecha.
    """
    texto = _normalizar(texto)
    numeros = list(re.finditer(r'\d+', texto))
    blocos = []
    for indice, match in enumerate(numeros):
        inscricao = match.group()
        if not 8 <= len(inscricao) <= 14:
            continue
        # Coleta as nove posições imediatamente seguintes ao identificador.
        candidatos = [
            int(item.group()) for item in numeros[indice + 1:indice + 10]
            if len(item.group()) <= 7
        ]
        if len(candidatos) < 9:
            continue
        qtd = candidatos[:9]
        if qtd[8] != sum(qtd[:8]):
            continue
        blocos.append({'codigo_propriedade': inscricao, 'quantidades': qtd})
    return blocos


def dados_go_ir(texto: str) -> list[dict]:
    dados = []
    for bloco in extrair_blocos(texto):
        qtd = bloco['quantidades']
        dados.append({
            'fazenda': '',
            'codigo_propriedade': bloco['codigo_propriedade'],
            'animais': {
                'f00_M': qtd[0], 'f00_F': qtd[1],
                'f05_M': 0, 'f05_F': 0,
                'f13_M': qtd[2], 'f13_F': qtd[3],
                'f25_M': qtd[4], 'f25_F': qtd[5],
                'fac_M': qtd[6], 'fac_F': qtd[7],
            },
            'total': qtd[8],
        })
    return dados


def read(text, **kwargs):
    from .base_reader import registros_do_parse
    from .mapping_loader import load_mapping

    blocos = dados_go_ir(text)
    registros = []
    for numero, dados in enumerate(blocos, start=1):
        registros.extend(registros_do_parse(
            dados,
            estado='GO',
            modelo='GO IR',
            arquivo=kwargs.get('arquivo', ''),
            numero_ficha=numero,
            mapping=kwargs.get('mapping') or load_mapping(),
        ))
    return {
        'sucesso': bool(blocos),
        'origem': 'GO_IR',
        'modelo': 'GO IR',
        'registros': registros,
        'dados_brutos': blocos,
        'avisos': [] if blocos else ['Nenhum bloco GO IR fechou com o total informado.'],
        'erros': [] if blocos else ['Ficha GO IR não reconhecida.'],
    }
