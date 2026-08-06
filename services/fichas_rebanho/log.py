"""Formato de LOG equivalente à aba LOG do XLSM."""


def registros_para_log(registros: list[dict]) -> list[dict]:
    campos = (
        'arquivo', 'fazenda', 'estado', 'especie', 'sexo',
        'estratificacao', 'quantidade', 'motivo', 'tabela_destino',
        'status', 'chave', 'numero_ficha',
    )
    return [{campo: registro.get(campo, '') for campo in campos}
            for registro in (registros or [])]
