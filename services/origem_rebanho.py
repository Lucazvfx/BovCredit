"""De onde vieram as quantidades do rebanho, e o que isso permite concluir.

Nenhum caminho de entrada conta boi. Nem o PDF: a GTA e a ficha sanitária são
DECLARAÇÃO do produtor ao órgão estadual, que registra o que recebeu — não faz
contagem em campo. A planilha e a digitação não têm nem esse registro.

Isso importa porque o rebanho é a garantia e é a origem de toda a receita
projetada. Um parecer que apresenta o DSCR com duas casas decimais sobre um
efetivo que ninguém conferiu passa uma precisão que o dado não tem, e quem lê
no comitê não tem como saber disso a menos que esteja escrito.

O aviso é específico por origem em vez de um disclaimer único porque as três
não são equivalentes: a ficha estadual deixa rastro documental oponível ao
produtor, a planilha e a digitação não deixam nada. Disclaimer que serve para
tudo é disclaimer que ninguém lê.
"""
from __future__ import annotations

ORIGENS = ('PDF', 'EXCEL', 'MANUAL')

_FONTE = {
    'PDF': 'ficha sanitária ou GTA emitida por órgão estadual de defesa agropecuária',
    'EXCEL': 'planilha preenchida fora do sistema',
    'MANUAL': 'digitação direta do analista',
}

_RASTRO = {
    'PDF': (
        'A ficha é declaração do produtor ao órgão estadual, que registra sem '
        'contar em campo — há rastro documental oponível, não verificação.'
    ),
    'EXCEL': (
        'A planilha não tem emissor oficial: o conteúdo é declaração sem '
        'registro em órgão de defesa.'
    ),
    'MANUAL': (
        'Os números foram digitados no sistema e não têm documento de origem '
        'anexado a esta análise.'
    ),
}

# Quanto o efetivo declarado é oponível a terceiros, não quanto é "confiável".
_RASTREABILIDADE = {'PDF': 'documental', 'EXCEL': 'declaratória', 'MANUAL': 'sem documento'}


def normalizar(origem: str | None) -> str:
    o = (origem or 'MANUAL').strip().upper()
    return o if o in ORIGENS else 'MANUAL'


def origem_rebanho(origem: str | None) -> dict:
    """Descreve a procedência do efetivo para a tela e para o PDF.

    Uma fonte só, porque tela e papel divergirem sobre a validade do dado é
    pior do que nenhum dos dois avisar.
    """
    o = normalizar(origem)
    return {
        'origem': o,
        'fonte': _FONTE[o],
        'rastreabilidade': _RASTREABILIDADE[o],
        'preliminar': True,
        'aviso': (
            f'Análise preliminar — efetivo não verificado. As quantidades vieram de '
            f'{_FONTE[o]}. {_RASTRO[o]} '
            f'A contratação deve exigir conferência do rebanho na origem.'
        ),
    }
