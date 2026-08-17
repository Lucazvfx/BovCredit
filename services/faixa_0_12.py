"""Regra única para quebrar a faixa de 0 a 12 meses nas duas posições jovens.

O vetor do motor tem duas posições para o animal de até um ano:

    posição 0/1   f00   a mais nova
    posição 2/3   f05   a mais velha

Boa parte das fichas estaduais (MS, MA, TO, RO, PA, GO, GO IR) declara uma
faixa só, "0 a 12 meses", e alguém precisa decidir como distribuí-la. A regra
aqui é metade para cada, com o ímpar sobrando para f05.

POR QUE ELA E NÃO OUTRA: é a que os parsers já aplicavam, é a que o README
documenta e é a distribuição em que `gestao_model.pkl` foi treinado — no
dataset sintético a mediana de f05F/f00F é 0,545 e só 14% das linhas têm f05F
zerado. Jogar a faixa inteira na primeira posição, como a consolidação
estadual fazia, empurra a entrada para essa cauda de 14% e degrada a
classificação sem que nada no sistema avise.

Ela NÃO é proporcional à duração das faixas, e nem poderia ser sem uma
decisão prévia: o repositório carrega três definições diferentes para os
mesmos dois slots (0–4/5–12 no catálogo estadual, 0–5/5–13 nos nomes de
feature do ml_engine, 0–6/7–12 nos padrões do pdf_parsers). Trocar a regra
exige fixar as faixas primeiro e retreinar depois.

AMBOS OS NÚMEROS SÃO ESTIMADOS. A ficha informou o total do ano; a divisão
entre as duas metades é inferência desta função.
"""


def dividir_0_12(quantidade: int) -> tuple[int, int]:
    """Devolve (f00, f05) para uma faixa declarada de 0 a 12 meses."""
    qtd = max(int(quantidade or 0), 0)
    metade = qtd // 2
    return metade, qtd - metade
