# Módulo agrícola: culturas perenes (café e cana)

**Data:** 2026-08-20
**Status:** Desenho para discussão — nada implementado
**Escopo escolhido:** módulo separado da pecuária · culturas perenes · leitura de
documento como entrada · custeio e investimento na mesma operação

## Objetivo

Estender a plataforma para emitir parecer de crédito sobre lavoura perene, sem
tocar no fluxo pecuário existente. Uma análise é agrícola ou pecuária; fazenda
mista fica fora deste desenho.

## A ressalva que vai antes do resto

Das quatro decisões, três apontam para o caminho mais exigente. Vale explicitar
antes de qualquer linha de código, porque muda a ordem do trabalho — não o
destino.

**1. Perene não tem safra; tem curva.** Soja é um número por ano: área ×
produtividade. Café e cana não são. A receita de um talhão depende da idade
dele, e a projeção de cinco anos é a soma de talhões em estágios diferentes.
Dois fenômenos decidem o parecer:

- **Bienalidade do café** — o cafeeiro alterna ano de carga alta e ano de carga
  baixa. Um DSCR calculado sobre um ano de carga alta aprova operação que quebra
  no ano seguinte.
- **Decaimento da soqueira na cana** — cada corte rende menos que o anterior,
  até a reforma do canavial. A receita cai ao longo do próprio contrato.

Nos dois casos **o ano crítico não é o ano 1**. Isso é bom: o motor já avalia
todos os anos do prazo (`avaliar_capacidade_no_prazo`, em
`services/payment_capacity_engine/dscr.py`), e essa decisão foi tomada no lado
pecuário justamente por isso. O que falta é o modelo de produção que alimenta
esses anos.

**2. Ler documento resolve o dado secundário, não o principal.** No lado
pecuário os parsers funcionam porque a ficha estadual tem layout fixo por órgão
— IDARON não muda de forma entre duas fazendas. Na lavoura perene:

- O **CAR** tem extrato padronizado (SICAR) e dá área, módulos fiscais,
  reserva legal, APP, sobreposição. Útil, e parseável.
- O CAR **não diz a idade do talhão** — que é exatamente o dado que decide a
  receita dos próximos cinco anos.
- Quem diz é o **laudo agronômico** ou o croqui do produtor, e esses não têm
  padrão nenhum: cada consultoria tem o seu.
- A **nota fiscal de venda** dá produtividade realizada, que é o melhor dado
  disponível para calibrar — e vem em layout de NF-e, parseável.

Então: parsear CAR e NF-e vale a pena e é factível. Parsear laudo agronômico é
trabalho aberto, e o dado que ele traz precisa existir de qualquer jeito. A
composição de talhões vai precisar de entrada estruturada — do mesmo modo que a
composição do rebanho tem a ficha .xlsx.

**3. Custeio e investimento juntos casam bem com perene.** É o caso natural:
financia-se a formação da lavoura (investimento, com carência até a primeira
colheita) e o custeio anual dela. O motor de crédito já faz carência,
periodicidade anual e SAC/Price — nada novo aqui.

**Consequência para a ordem do trabalho:** o modelo econômico da perene é o que
não existe em lugar nenhum e é o que dá valor. O parsing de documento é
incremental e pode entrar depois sem retrabalho, desde que o contrato de dados
já preveja de onde cada campo veio (é o que `services/proveniencia.py` já faz).
Este desenho entrega os dois, nessa ordem.

## O que já existe e serve sem alteração

O miolo de crédito não sabe que é boi. As funções recebem dicionário:

```
calculate_costs(production, cost_parameters)        economic_engine/costs.py
calculate_revenues(production, prices)              economic_engine/revenues.py
calculate_payment_capacity(cashflow, ...)           payment_capacity_engine/dscr.py
project_cashflow(annual_projection, ...)            cashflow_engine/monthly.py
run_stress_tests(base_analysis, scenarios)          stress_engine/scenarios.py
```

Reaproveitam inteiros: DSCR, Price/SAC, cronograma com periodicidade, crédito
máximo, fluxo mensal, sazonalidade, cenários de estresse, rating, checklist,
endividamento, garantia, parecer PDF, qualidade de dados, proveniência,
auditoria, multiempresa, LGPD, autenticação.

`services/ibge_sidra.py` é genérico (`baixar(tabela, variavel, periodo)`) e hoje
puxa abate e efetivo. As mesmas funções puxam a **PAM (tabela 5457)** — área
colhida, quantidade produzida e rendimento médio por município e cultura, café e
cana inclusos. É benchmark de produtividade municipal quase de graça, e é o que
permite dizer "a produtividade declarada está 40% acima da média do município".

## O que é específico de boi e precisa de par agrícola

`production_engine` · `livestock_engine` · `ml_engine` (classificação de ciclo) ·
`pdf_parsers` e `fichas_rebanho` · `pesos_rebanho` · `custos_desembolso` (@/cab) ·
`parametros_zootecnicos` · `consistencia_rebanho` · `validacao_zootecnica` ·
`_category_specs()` em `economic_engine/revenues.py`.

## O modelo: talhão é coorte

A forma já existe no projeto. `production_engine` projeta coortes de animais por
faixa etária ao longo dos anos; a lavoura perene é a mesma estrutura com outro
conteúdo — **talhões agrupados por ano de plantio**, cada um com sua curva.

```
Talhao(cultura, area_ha, ano_plantio, variedade, espacamento, irrigado)
   -> idade no ano N
   -> estagio(idade)          formação | produção | declínio | reforma
   -> produtividade(idade, estagio, fase_bienal)
   -> receita = area * produtividade * preco - custo_ha(estagio)
```

O projetor soma os talhões por ano e devolve a mesma forma que o motor econômico
já consome hoje. Nada a jusante muda.

### Café

- **Formação**: sem receita nos primeiros anos; primeira colheita comercial
  parcial, produção plena depois.
- **Produção**: vida útil longa, com **bienalidade** — carga alta e carga baixa
  alternadas. A amplitude varia com manejo, adubação e clima.
- **Renovação**: recepa/esqueletamento zera a produção do talhão por um ou dois
  anos e reinicia o ciclo. Um plano de recepa dentro do prazo do contrato é
  material para o DSCR e precisa ser declarado.
- Unidade: saca de 60 kg beneficiada. Preço com diferencial por tipo/bebida.

### Cana

- **Cana planta**: intervalo entre plantio e primeiro corte.
- **Soqueiras**: cortes sucessivos com produtividade decrescente a cada corte,
  até a reforma do talhão.
- Unidade: tonelada, remunerada por **ATR** (açúcar total recuperável) em contrato
  com usina — o preço não é do produto, é do teor. Modelar como preço/ton com
  qualidade declarada, e registrar que o dado veio do contrato de fornecimento.

**Todos os parâmetros numéricos acima ficam de fora deste documento de
propósito.** No lado pecuário, cada constante tem origem declarada
(`services/proveniencia.py`: medido, referência bibliográfica ou política da
instituição). Os parâmetros de café e cana entram pelo mesmo caminho, com fonte
citável — Embrapa Café, Embrapa/IAC, Conab, CEPEA — e não por estimativa
inventada aqui. Enquanto não houver fonte, o campo é entrada do analista com
aviso de qualidade de dado.

## Entrada de dados

| Documento | O que dá | Layout | Fase |
|---|---|---|---|
| Composição de talhões (.xlsx nosso) | área, ano de plantio, cultura, variedade | nosso | 1 |
| CAR / extrato SICAR | área total, reserva legal, APP, sobreposição | padronizado | 2 |
| NF-e de venda | produtividade realizada, preço praticado | padronizado | 2 |
| Laudo agronômico | idade e estado do talhão | sem padrão | 3, se houver demanda |

A ficha de talhões reaproveita a infraestrutura de
`scripts/generate_ficha_consolidado.py` e `services/importar_excel.py` — mesmo
formato de bloco, sem macro.

## Fases, com critério de verificação

```
1. Modelo de produção perene (talhão como coorte)
   verificar: projeção de 6 anos de um cafezal com bienalidade e de um canavial
   com decaimento; soma dos talhões bate com a soma manual; o ano crítico do
   DSCR cai num ano de carga baixa, não no ano 1

2. Receita e custo por cultura (par agrícola de _category_specs)
   verificar: receita de saca e de tonelada com preço declarado; custo por
   hectare separado por estágio (formação não tem receita mas tem custo)

3. Ficha de talhões .xlsx + importação
   verificar: round-trip preenche e importa, como o teste da ficha de rebanho

4. Parecer agrícola ponta a ponta
   verificar: rota nova devolve DSCR, cronograma, cenários e PDF, usando os
   motores existentes sem duplicar fórmula

5. Benchmark IBGE/PAM por município
   verificar: produtividade declarada comparada à média municipal, com a mesma
   ressalva de proxy que o desfrute já carrega

6. CAR e NF-e (parsing)
   verificar: extrato SICAR devolve área e regularidade; NF-e devolve
   quantidade e preço, com a origem registrada na proveniência
```

## O que este desenho NÃO entrega

- Fazenda mista (lavoura + pecuária no mesmo parecer) — decisão explícita.
- Culturas anuais (soja, milho, algodão).
- Parsing de laudo agronômico.
- Seguro agrícola, Proagro e zoneamento agrícola de risco climático.
- Qualquer parâmetro agronômico sem fonte citável.
