from __future__ import annotations

from pathlib import Path

from .mapping_loader import MappingCatalog, load_mapping


_FAIXAS_10 = {
    'f00_F': ('FEMEA', '00 A 04 MESES'),
    'f05_F': ('FEMEA', '05 A 12 MESES'),
    'f13_F': ('FEMEA', '13 A 24 MESES'),
    'f25_F': ('FEMEA', '25 A 36 MESES'),
    'fac_F': ('FEMEA', 'ACIMA DE 36 MESES'),
    'f00_M': ('MACHO', '00 A 04 MESES'),
    'f05_M': ('MACHO', '05 A 12 MESES'),
    'f13_M': ('MACHO', '13 A 24 MESES'),
    'f25_M': ('MACHO', '25 A 36 MESES'),
    'fac_M': ('MACHO', 'ACIMA DE 36 MESES'),
}

_MODELOS_QUATRO_FAIXAS = {
    'MS', 'MA', 'TO_DECLARACAO', 'RO_DECLARACAO',
    'PA_DECLARACAO', 'GO_DECLARACAO', 'GO IR', 'RESUMO_FAZENDAS',
}


def _modelo(estado: str | None, modelo: str | None, origem: str) -> str:
    if modelo:
        return modelo.strip().upper()
    if estado:
        uf = estado.strip().upper()
        return {
            'MT': 'MT_DECLARACAO',
            'RO': 'RO_DECLARACAO',
            'MS': 'MS',
            'GO': 'GO_DECLARACAO',
            'MA': 'MA',
            'TO': 'TO_DECLARACAO',
            'PA': 'PA_DECLARACAO',
        }.get(uf, origem)
    return {
        'DECLARACAO_IDARON': 'RO_DECLARACAO',
        'IDARON': 'RO_DECLARACAO',
        'INDEA': 'MT_DECLARACAO',
        'AGRODEFESA_GO': 'GO_DECLARACAO',
        'GO_DEC_WEB': 'GO_DECLARACAO',
        'IAGRO_MS': 'MS',
        'AGED_MA': 'MA',
        'ADAPEC_TO': 'TO_DECLARACAO',
        'ADEPARA_PA': 'PA_DECLARACAO',
    }.get(origem, origem)


def _parser(origem: str, text: str, pdf_path: str | None = None) -> dict:
    from pdf_parsers import (
        parsear_adapec_to,
        parsear_adepara_pa,
        parsear_aged_ma,
        parsear_agrodefesa_go,
        parsear_declaracao_idaron,
        parsear_generico,
        parsear_idaron,
        parsear_iagro_ms,
        parsear_indea,
        parsear_resumo_fazendas,
        parsear_go_declaracao_web,
    )

    if origem == 'RESUMO_FAZENDAS':
        return parsear_resumo_fazendas(text, pdf_path=pdf_path)
    if origem == 'DECLARACAO_IDARON':
        return parsear_declaracao_idaron(text)
    if origem == 'IDARON':
        return parsear_idaron(text, pdf_path=pdf_path)
    if origem == 'INDEA':
        return parsear_indea(text, pdf_path=pdf_path)
    if origem == 'IAGRO_MS':
        return parsear_iagro_ms(text)
    if origem == 'AGED_MA':
        return parsear_aged_ma(text)
    if origem == 'GO_DEC_WEB':
        return parsear_go_declaracao_web(text)
    if origem == 'AGRODEFESA_GO':
        return parsear_agrodefesa_go(text)
    if origem == 'ADAPEC_TO':
        return parsear_adapec_to(text, pdf_path=pdf_path)
    if origem == 'ADEPARA_PA':
        return parsear_adepara_pa(text)
    return parsear_generico(text)


def _origem_do_modelo(modelo: str, detectada: str) -> str:
    if modelo == 'GO_DECLARACAO' and detectada == 'GO_DEC_WEB':
        return 'GO_DEC_WEB'
    return {
        'MT_DECLARACAO': 'INDEA',
        'RO_DECLARACAO': 'IDARON',
        'MS': 'IAGRO_MS',
        'GO_DECLARACAO': 'AGRODEFESA_GO',
        'MA': 'AGED_MA',
        'TO_DECLARACAO': 'ADAPEC_TO',
        'PA_DECLARACAO': 'ADEPARA_PA',
    }.get(modelo, detectada)


def registros_do_parse(
    dados: dict,
    estado: str,
    arquivo: str = '',
    mapping: MappingCatalog | None = None,
    numero_ficha: int = 1,
    modelo: str | None = None,
) -> list[dict]:
    catalog = mapping or load_mapping()
    modelo = _modelo(estado, modelo, estado)

    # Relatórios "Rebanho por Fazenda" trazem várias propriedades no mesmo
    # PDF. Preservamos a granularidade no fluxo de importação; o consolidado
    # geral continua sendo obtido pela soma dos registros abaixo.
    if modelo == 'RESUMO_FAZENDAS' and dados.get('fazendas'):
        registros_por_fazenda = []
        for indice, fazenda in enumerate(dados['fazendas'], start=1):
            registros_por_fazenda.extend(registros_do_parse(
                fazenda, estado, arquivo=arquivo, mapping=catalog,
                numero_ficha=indice, modelo=modelo))
        return registros_por_fazenda

    animais = dados.get('animais') or {}
    registros = []

    for chave_animal, (sexo, faixa_dez) in _FAIXAS_10.items():
        quantidade = animais.get(chave_animal, 0) or 0
        faixa = faixa_dez
        if modelo in _MODELOS_QUATRO_FAIXAS and chave_animal in {
            'f00_F', 'f05_F', 'f00_M', 'f05_M',
        }:
            faixa = '0 A 12 MESES'
            # O parser interno separa f00/f05 para compatibilidade com o
            # motor atual; o mapeamento estadual de quatro faixas soma ambos.
        regra = catalog.lookup(modelo, sexo, faixa)
        registro = {
            'arquivo': arquivo,
            'fazenda': dados.get('fazenda', ''),
            'municipio': dados.get('municipio', ''),
            'estado': modelo,
            'especie': 'BOVINO',
            'sexo': sexo,
            'estratificacao': faixa,
            'quantidade': quantidade,
            'numero_ficha': numero_ficha,
            'codigo_propriedade': dados.get('codigo_propriedade', ''),
            'chave': regra.chave if regra else f'{modelo}|{sexo}|{faixa}',
            'classificacao': regra.classificacao if regra else '',
            'tabela_destino': (
                f'tab{"femea" if sexo == "FEMEA" else "macho"}_{numero_ficha}'
                if regra else ''
            ),
            'status': 'Distribuído' if regra else 'Revisão',
            'motivo': '' if regra else 'Código não identificado no MAPEAMENTO.',
        }
        registros.append(registro)

    # Une os dois blocos jovens para modelos de quatro faixas.
    if modelo in _MODELOS_QUATRO_FAIXAS:
        unificados = []
        for sexo in ('FEMEA', 'MACHO'):
            jovens = [
                r for r in registros
                if r['sexo'] == sexo and r['estratificacao'] == '0 A 12 MESES'
            ]
            if jovens:
                base = dict(jovens[0])
                base['quantidade'] = sum(r['quantidade'] for r in jovens)
                unificados.append(base)
        registros = [
            r for r in registros
            if not (
                r['estratificacao'] == '0 A 12 MESES'
                and r['sexo'] in ('FEMEA', 'MACHO')
            )
        ] + unificados
    return registros


def read_ficha_text(
    text: str,
    estado: str | None = None,
    modelo: str | None = None,
    arquivo: str = '',
    pdf_path: str | None = None,
) -> dict:
    from pdf_parsers import detectar_origem

    if not text or not text.strip():
        return {
            'sucesso': False,
            'origem': None,
            'modelo': modelo,
            'registros': [],
            'avisos': [],
            'erros': ['PDF sem texto extraível.'],
        }
    origem = detectar_origem(text)
    modelo_real = _modelo(estado, modelo, origem)
    # A declaraÃ§Ã£o web de GO possui cinco faixas; o modelo GO_DECLARACAO
    # manual continua representando o layout de quatro faixas.
    if not estado and not modelo and origem == 'GO_DEC_WEB':
        modelo_real = 'GO_DEC_WEB'
    if modelo_real == 'GO IR':
        from .reader_go_ir import read as read_go_ir
        return read_go_ir(text, arquivo=arquivo)
    dados = _parser(_origem_do_modelo(modelo_real, origem), text, pdf_path=pdf_path)
    registros = registros_do_parse(
        dados, modelo_real, arquivo=arquivo, modelo=modelo_real)
    for registro in registros:
        registro.setdefault('origem', origem)
        registro.setdefault('modelo', modelo_real)
    # O parser roda até o fim mesmo quando não reconhece nenhuma linha e
    # devolve as dez faixas zeradas. Um contrato ou um layout não suportado
    # tem texto extraível e chegaria aqui como leitura bem-sucedida — o
    # rebanho vazio seguiria para classificação e parecer como dado observado.
    if not any(
        (registro.get('quantidade') or 0) > 0 for registro in registros
    ):
        return {
            'sucesso': False,
            'origem': origem,
            'modelo': modelo_real,
            'dados_brutos': dados,
            'registros': [],
            'avisos': [],
            'erros': [
                'Nenhuma categoria de animal foi reconhecida — '
                'layout não suportado ou ficha sem rebanho.'
            ],
        }
    return {
        'sucesso': True,
        'origem': origem,
        'modelo': modelo_real,
        'dados_brutos': dados,
        'registros': registros,
        'avisos': [],
        'erros': [],
    }


def read_ficha_pdf(
    file_path: str | Path,
    estado: str | None = None,
    modelo: str | None = None,
) -> dict:
    from pdf_parsers import extrair_texto_pdf

    path = Path(file_path)
    try:
        text = extrair_texto_pdf(str(path))
    except Exception as exc:
        return {
            'sucesso': False,
            'origem': None,
            'modelo': modelo,
            'registros': [],
            'avisos': [],
            'erros': [f'Falha na extração do PDF: {exc}'],
        }
    return read_ficha_text(
        text,
        estado=estado,
        modelo=modelo,
        arquivo=path.name,
        pdf_path=str(path),
    )
