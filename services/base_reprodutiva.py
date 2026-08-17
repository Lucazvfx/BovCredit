"""Definição única de quem, no vetor de dez posições, produz bezerro.

O vetor tem duas faixas de fêmea adulta e elas não são a mesma coisa:

    v[6]  fêmeas de 25 a 36 meses    ainda NÃO pariram
    v[8]  fêmeas acima de 36 meses   estão em reprodução

Embrapa Gado de Corte mediu 36,3 meses de idade média à primeira parição em
468 matrizes Nelore; no Pantanal extensivo (CT 126) são 40,0. Uma fêmea de 30
meses é novilha, não matriz — projetar bezerro em cima dela cria produção que
a fazenda não tem.

Isso já foi corrigido nos motores de produção (`test_base_reprodutiva.py`),
mas cada consumidor recalculava a base inline, com duas fórmulas diferentes
espalhadas por cinco arquivos. `consistencia_rebanho.py` chegou a registrar a
divergência em comentário e deixá-la aberta, porque acertar de um lado só
faria os dois números discordarem no mesmo parecer.

Este módulo existe para que a escolha seja feita UMA vez e cada chamador diga
qual número está usando:

    `matrizes`         projeção de nascimento, desmama e reposição
    `prestes`          a coorte que entra no plantel no próximo ciclo
    `plantel_adulto`   composição, valorização e features do classificador

RESSALVA SOBRE `matrizes`: numa ficha etária ninguém comprova parição. v[8] é
aproximação conservadora — "passou da idade de primeira cria" —, não fato
observado. Quando o número real de matrizes vier informado, ele deve
prevalecer sobre esta inferência.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BaseReprodutiva:
    matrizes: float
    prestes: float

    @property
    def plantel_adulto(self) -> float:
        """Fêmeas adultas em estoque — as duas faixas somadas.

        É o número certo para composição do rebanho, valorização patrimonial
        e features do classificador: para dizer se um rebanho é de cria, a
        fêmea de 30 meses conta tanto quanto a de 40. Só não serve para
        projetar bezerro.
        """
        return self.matrizes + self.prestes


def base_reprodutiva(valores) -> BaseReprodutiva:
    """Lê a base reprodutiva do vetor de dez posições."""
    v = list(valores)
    if len(v) < 10:
        return BaseReprodutiva(matrizes=0.0, prestes=0.0)
    return BaseReprodutiva(matrizes=float(v[8]), prestes=float(v[6]))
