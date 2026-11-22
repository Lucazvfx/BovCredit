# Desfecho do parecer: o que aconteceu depois

**Data:** 2026-08-22
**Status:** Desenho para discussão — nada implementado
**Escopo:** registrar o desfecho real de cada parecer emitido, e ligar esse
desfecho à análise que o produziu.

## Objetivo

O sistema emite parecer e nunca pergunta o que aconteceu. Busca por `desfecho`,
`inadimpl`, `foi_pago` no repositório não devolve nada: não há campo, não há
tabela, não há tela.

O próprio código já declara a consequência disso. Em
`services/rating_credito.py`:

> *"Rating indicativo. Deve ser calibrado com histórico real de operações pagas
> e inadimplentes."*

Hoje o classificador é treinado em dado sintético (`treinar_ciclos.py`) e
validado contra quatro casos rotulados por especialista
(`tests/test_casos_material_treinamento.py`). Não é pouco para começar — é
insuficiente para afirmar acurácia, e o projeto já diz isso em vários lugares.

Este desenho fecha o ciclo.

## Por que isto, e não outra funcionalidade

Funcionalidade se copia num sprint. Dado com desfecho, não.

Cada parecer emitido com desfecho registrado vira um par **(o que o sistema
disse × o que aconteceu)**. Em dois anos isso é um conjunto de decisões reais de
crédito pecuário brasileiro com resultado conhecido — que não se compra, não se
raspa e cresce sozinho a cada análise. É a diferença entre um produto que
calcula e um produto que aprendeu.

Vale registrar o que este desenho **não** promete: não é retreino automático do
modelo. Volume pequeno e enviesado piora modelo em vez de melhorar. Aqui se
constrói a coleta e a medição da coleta; o que fazer com o dado é decisão
posterior, com o dado na mão.

## O que já existe — metade do caminho

| Peça | Onde | Serve para |
|---|---|---|
| `pareceres` | `database.py:629` | o que foi emitido: recomendação, DSCR, solicitação |
| `analysis_snapshots` | `database.py:168` | reproduzir a análise exata: payload, contexto, resultado, versão |
| `casos_reais` | `database.py:583` | rótulo humano do ciclo, com `PENDENTE / CONFIRMADO / DESCARTADO` |
| `auditoria_acessos` | — | trilha de quem registrou o quê |
| `services/lgpd.py` | `INVENTARIO` | registro do Art. 37, onde a tabela nova precisa entrar |

O `analysis_snapshots` é o que dá valor ao desfecho: sem ele, "essa operação
quebrou" é anedota; com ele, é o resultado confrontável com a projeção, os
preços e a versão do motor daquele dia.

## O dado mínimo

A tentação é um formulário de vinte campos que ninguém preenche. O desfecho útil
cabe em três perguntas, feitas em momentos diferentes:

**1. A operação saiu?** — `contratada` · `recusada` · `desistiu` · `nao_sei`
Se saiu: valor, prazo, taxa e sistema **contratados** — que costumam divergir do
que foi pedido, e essa divergência é informação.

**2. Está sendo paga?** — por marco (safra, parcela ou semestre):
`em_dia` · `atraso_ate_30` · `atraso_31_90` · `atraso_mais_90` · `renegociada`
· `liquidada` · `nao_sei`

**3. Por quê?** — texto livre curto, opcional. É onde aparece o que nenhum
campo previu: seca, doença no rebanho, preço da arroba, problema de gestão.

### "Não sei" é resposta, e é diferente de silêncio

Mesma regra que o projeto já aplica em `validacao_zootecnica`: checagem que não
rodou não pode parecer checagem que passou. Aqui:

- **não respondido** — ninguém perguntou ou ninguém voltou
- **`nao_sei`** — perguntaram, o analista não tem a informação

Tratar os dois como o mesmo estado esconde a taxa de resposta real, que é o
número que diz se o conjunto presta.

### O desfecho ruim vale mais que o bom

Crédito recusado pelo banco e operação que quebrou são os casos que mais
ensinam, e são os que ninguém tem vontade de registrar. A tela precisa tornar o
registro de recusa tão fácil quanto o de sucesso — sem confirmação extra, sem
tom de erro.

## Viés de sobrevivência — o risco central deste desenho

Se só os desfechos bons forem registrados, o modelo aprende que quase tudo dá
certo, e o rating fica pior do que é hoje. Três defesas, todas obrigatórias:

1. **Medir a taxa de resposta** por consultoria e por recomendação emitida. Se
   pareceres com recomendação "negar" respondem menos que os "aprovar", o
   conjunto está torto e o painel tem de dizer isso.
2. **Nunca preencher desfecho por inferência.** Nada de "sem notícia = pagou".
3. **Publicar a cobertura junto de qualquer número derivado.** Rating calibrado
   sobre 12% dos pareceres não é rating calibrado — é amostra de conveniência,
   e o parecer precisa dizer sobre quantos casos ele se apoia.

## Quando perguntar

Lembrete, não formulário permanente. A pergunta certa no momento em que o
analista tem a resposta:

```
emissão + ~60 dias   →  "a operação saiu?"       (1 pergunta, 3 cliques)
contratada + safra   →  "está sendo paga?"        (1 pergunta, por marco)
a qualquer momento   →  registrar do histórico    (quando ele já sabe)
```

O lembrete vive no Histórico, ao lado do parecer, não como notificação
intrusiva. Nenhuma etapa é obrigatória e nenhuma trava a ferramenta.

## Modelo de dados

Tabela nova, aditiva, sem tocar em `pareceres`:

```
desfechos
  id
  parecer_id          FK pareceres
  snapshot_id         FK analysis_snapshots  (nulo quando não houver)
  empresa_id, user_id                        (quem registrou)
  etapa               'contratacao' | 'adimplencia'
  situacao            enum das listas acima
  valor_contratado, prazo_contratado, juros_contratado, sistema_contratado
  competencia         a que safra/parcela o marco se refere
  observacao          texto curto
  created_at
```

Um parecer tem **muitos** desfechos: a contratação é um registro, cada marco de
adimplência é outro. Histórico, não campo sobrescrito — trocar "em dia" por
"atraso" apagando o anterior perderia justamente a trajetória.

## LGPD — obrigatório neste repositório

`services/lgpd.py` é explícito: *"tabela nova com dado pessoal e sem entrada
aqui é buraco de conformidade"*. `desfechos` carrega **dado financeiro de
terceiro** — a situação de pagamento de um produtor identificável — e é
provavelmente o dado mais sensível que o sistema passará a guardar.

Entrada a acrescentar no `INVENTARIO`:

- **titular**: cliente da consultoria (produtor)
- **finalidade**: acompanhar o resultado da recomendação emitida e calibrar o
  modelo de risco da própria consultoria
- **retenção**: a definir com o encarregado — não herdar por descuido a de
  auditoria
- **base legal**: a discutir. Legítimo interesse é defensável para a consultoria
  acompanhar o próprio parecer; usar o dado para treinar modelo que serve outras
  consultorias é finalidade distinta e precisa de decisão própria.

Esse último ponto não é detalhe jurídico solto: se o dado só puder ser usado
dentro da consultoria que o coletou, o fosso é menor e o desenho do produto
muda. **Resolver antes de implementar a fase 3.**

## O que isto destrava

- **Rating deixa de ser indicativo** — quando houver volume e cobertura que
  sustentem, e não antes
- **Retreino com caso real** em vez de sintético, com o par projeção × desfecho
- **Acurácia mensurável**: "das operações que recomendamos aprovar, quantas
  foram pagas?" é a única pergunta que valida a ferramenta
- **Calibração por região e modalidade** — o que funciona em RO pode não valer
  em MT
- **Argumento comercial verificável**: taxa de acerto medida em vez de afirmada

## Fases, com critério de verificação

```
1. Tabela, entrada no INVENTARIO e API de registro
   verificar: um parecer aceita vários desfechos; 'nao_sei' e ausência são
   estados distintos e distinguíveis na consulta

2. Registro pelo Histórico, sem lembrete
   verificar: registrar contratação e adimplência em 3 cliques; recusa tão
   fácil quanto aprovação; nada obrigatório

3. Vínculo com o snapshot e painel de cobertura
   verificar: dado o desfecho, reproduzir a análise original; o painel mostra
   taxa de resposta por recomendação emitida e acusa o viés quando ele existe

4. Lembrete no tempo certo
   verificar: aparece aos ~60 dias, some quando respondido, nunca trava a tela

5. Medição de acerto — só depois de cobertura suficiente
   verificar: o número sai acompanhado de sobre quantos casos ele se apoia
```

## O que este desenho NÃO entrega

- Retreino automático do modelo
- Integração com SCR, bureau ou banco para buscar adimplência sozinho
- Score de crédito do produtor — isto mede o **parecer**, não a pessoa
- Qualquer número de acurácia antes de haver cobertura que o sustente
