"""A aba de cenários não pode contradizer o parecer no mesmo rebanho.

O defeito que estes testes travam: a aba alimentava seu campo "Matrizes" com
`v[6]+v[8]` — novilhas de 25–36m MAIS vacas — enquanto o parecer usa só
`v[8]`. Com 80 novilhas e 200 vacas a 65% de natalidade, a mesma tela mostrava
130 bezerros no parecer e 182 na aba: 40% de diferença, sem nada explicando
qual dos dois valia.

É a mesma confusão que services/base_reprodutiva.py resolveu no backend — uma
palavra respondendo a três perguntas diferentes. `ml_engine.py` até registra o
risco de ela voltar "só que na tela", que foi exatamente o que aconteceu.

Os testes leem o próprio index.html porque é lá que o defeito mora: um teste
de backend não o pegaria.
"""
import re
from pathlib import Path

import pytest

from services.base_reprodutiva import base_reprodutiva

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

# 80 novilhas de 25–36m (v[6]) e 200 vacas (v[8]) — a proporção que torna a
# divergência visível em vez de arredondamento.
REBANHO = [40, 40, 40, 40, 60, 60, 80, 50, 200, 10]
NATALIDADE = 0.65

_SO_INDICES = re.compile(r"^[\w\[\]\+\s]+$")


def _valor_atribuido(campo: str, variavel: str, vetor: list) -> float:
    """Avalia a expressão que o index.html atribui a um campo da aba.

    Ex.: para `getElementById('s-mat').value=v[8];` devolve vetor[8].
    """
    achados = re.findall(
        re.escape(f"getElementById('{campo}').value=") + r"([^;]+);", INDEX
    )
    expressoes = [e.strip() for e in achados if variavel in e]
    assert expressoes, f"nenhuma atribuição de {campo} a partir de {variavel}"

    valores = set()
    for expr in expressoes:
        assert _SO_INDICES.match(expr), f"expressão inesperada em {campo}: {expr}"
        valores.add(eval(expr, {"__builtins__": {}}, {variavel: vetor}))  # noqa: S307
    assert len(valores) == 1, (
        f"{campo} recebe valores diferentes em pontos diferentes: {valores}"
    )
    return valores.pop()


@pytest.mark.parametrize("variavel", ["v", "lastVals"])
def test_a_aba_recebe_as_matrizes_que_o_parecer_usa(variavel):
    """As duas sincronizações — automática e o botão "Sincronizar" — concordam."""
    esperado = base_reprodutiva(REBANHO).matrizes
    assert _valor_atribuido("s-mat", variavel, REBANHO) == esperado


@pytest.mark.parametrize("variavel", ["v", "lastVals"])
def test_a_aba_recebe_as_prestes_separadas(variavel):
    esperado = base_reprodutiva(REBANHO).prestes
    assert _valor_atribuido("s-prestes", variavel, REBANHO) == esperado


@pytest.mark.parametrize("variavel", ["v", "lastVals"])
def test_os_bezerros_da_aba_batem_com_os_do_parecer(variavel):
    """O teste que dá nome ao arquivo: mesmo rebanho, mesmo número de bezerros.

    Antes da correção este dava 182 contra 130.
    """
    mat_aba = _valor_atribuido("s-mat", variavel, REBANHO)
    bezerros_aba = int(mat_aba * NATALIDADE)
    bezerros_parecer = int(base_reprodutiva(REBANHO).matrizes * NATALIDADE)
    assert bezerros_aba == bezerros_parecer


def test_a_producao_de_bezerros_usa_so_quem_ja_pariu():
    """Novilha coberta não pare no mesmo ano — `prestes` fica fora daqui."""
    linha = re.search(r"const totBez=Math\.floor\(([^)]*)\)", INDEX)
    assert linha, "cálculo de totBez não encontrado"
    assert linha.group(1) == "mat*nat", linha.group(1)


def test_a_relacao_touro_femea_conta_as_duas_coortes():
    """Aqui `prestes` ENTRA: o touro cobre a novilha de 25–36m agora.

    É por isso que uma variável só não resolve — o mesmo número está certo
    para esta conta e errado para a de bezerros.
    """
    linha = re.search(r"const bNec=Math\.max\(1,Math\.ceil\(([^)]*)\)", INDEX)
    assert linha, "cálculo de bNec não encontrado"
    assert linha.group(1) == "plantelAdulto/prop", linha.group(1)


def test_o_descarte_nao_atinge_quem_nunca_pariu():
    linha = re.search(r"const desQ=Math\.floor\(([^)]*)\)", INDEX)
    assert linha, "cálculo de desQ não encontrado"
    assert linha.group(1) == "mat*des", linha.group(1)


def test_o_rebanho_total_nao_perde_as_novilhas():
    """Separar as coortes não pode fazer animal sumir da contagem nem do custo."""
    for nome in ("totReb", "totCusto"):
        linha = re.search(rf"const {nome}=([^;]+);", INDEX)
        assert linha, f"cálculo de {nome} não encontrado"
        assert "plantelAdulto" in linha.group(1), f"{nome}: {linha.group(1)}"
