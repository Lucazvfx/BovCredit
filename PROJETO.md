# BovCredit — o que o projeto tem e o que ele faz

Inventário técnico completo, levantado do código em 31/07/2026.

Este documento descreve o sistema **como ele está**, incluindo o que não
funciona e o que não foi validado. Para a apresentação comercial, veja o
`README.md`. Para o memorial de cálculo, o `CALCULOS.txt`. Para desligar
recursos sem mexer no código, o `REVERTER.md`.

> **Aviso sobre o `SISTEMA.txt`:** aquele documento está desatualizado — fala em
> Python 3.10, porta 5050 e quatro modalidades de ciclo. Hoje são Python 3.11.15
> e seis modalidades. Onde os dois divergirem, este vale.

---

## 1. O que é

Plataforma de análise de crédito rural para pecuária de corte. Recebe a
composição de um rebanho, classifica a modalidade de exploração, projeta a
geração de caixa ao longo do prazo do financiamento e emite um parecer com
recomendação **Aprovar / Ressalva / Negar**, com memória de cálculo passo a
passo.

O público é a consultoria de crédito e o analista de banco — não o produtor.

---

## 2. Números

| | |
|---|---|
| Python (produção) | 10.476 linhas |
| Interface (`templates/index.html`) | 3.750 linhas |
| Testes | **417** casos em 56 arquivos |
| Rotas HTTP | 44, sendo 25 endpoints `/api` |
| Modelo | ensemble de 4, 42 features, 6 classes |
| Agências estaduais lidas | 7 |
| Tabelas no banco | 11 |

---

## 3. O fluxo de uma análise

1. **Entrada** — 10 contagens por faixa etária e sexo, digitadas, importadas de
   Excel ou extraídas de um PDF de declaração estadual.
2. **Classificação** — o ensemble aponta a modalidade entre seis, com
   probabilidade, proveniência da decisão (regra ou ML) e índice de atipicidade.
3. **Praça** — informado o município, o preço nacional recebe o diferencial
   regional. Tudo abaixo herda esse preço.
4. **Simulação** — projeção plurianual por coortes etárias, no cenário
   conservador, com venda, compra, mortalidade e evolução de idade.
5. **Fluxo de caixa** — metodologia GEP Araguaia, incluindo variação de estoque
   do rebanho.
6. **Auditoria** — consistência do rebanho declarado, reconciliação de garantia
   entre documentos, desfrute contra a faixa da modalidade.
7. **Crédito** — DSCR em **todos** os anos do prazo, endividamento total,
   garantia pelo valor de execução.
8. **Parecer** — recomendação, memória de cálculo, explicação SHAP, PDF com a
   marca da consultoria.
9. **Confirmação** — o analista confirma ou corrige a modalidade, e isso vira
   dado de treino.

---

## 4. Motor de classificação — `ml_engine.py`

**Ensemble de quatro modelos votando:** RandomForest, GradientBoosting, XGBoost
e LightGBM.

**Entrada:** 10 contagens → **42 features** engenheiradas (proporções, razões
entre categorias, indicadores derivados).

**Saída:** uma de **seis** modalidades.

| Modalidade | Perfil |
|---|---|
| `CRIA` | matrizes dominam; receita é bezerro |
| `RECRIA` | poucos adultos, predomínio de jovens; ganho de peso intermediário |
| `ENGORDA` | confinamento; 85% em 13–24m, saída para abate |
| `CICLO_COMPLETO` | cria, recria e engorda integrados |
| `RECRIA_ENGORDA` | compra magro e termina; giro alto |
| `CRIA_RECRIA` | produção própria mais compra de desmama |

**Acurácia:** 91,2% ± 5,41 em validação cruzada, 34.902 amostras.

> **Ressalva que importa:** esse conjunto é **sintético**, gerado das faixas de
> referência que nós mesmos escrevemos em `treinar_ciclos.py`. O número mede que
> o modelo aprendeu as faixas, não que acerta na realidade. É validação circular,
> e é exatamente por isso que existe o botão de confirmação (§10).

**Também no motor:**
- **SHAP** (TreeExplainer) para explicabilidade — exigência da Res. CMN 4.966/2021
- **Proveniência** da decisão: regra determinística ou ML
- **Atipicidade**: o quanto o rebanho se afasta da distribuição de treino
- **Agrupamento de features redundantes** no SHAP (7 pares com correlação 1,0)

---

## 5. Leitura de documentos — `pdf_parsers.py`

1.375 linhas. **Sete agências estaduais de defesa agropecuária:**

| Agência | UF | Faixas etárias |
|---|---|---|
| INDEA | MT | 5 (0-4 / 5-12 / 13-24 / 25-36 / 36m+) |
| AGRODEFESA | GO | 5 |
| IDARON | RO | 4 (0-12 / 13-24 / 25-36 / 36m+) |
| IAGRO | MS | 4 |
| AGED | MA | 4 |
| ADAPEC | TO | 4 |
| ADEPARÁ | PA | 4 |

Extração em cascata: `pdftotext` → `pdfplumber` → OCR (Tesseract) para PDF
escaneado. Mais um parser genérico de fallback.

**É o fosso do projeto.** Formatos diferentes por estado, órgãos que mudam
layout sem avisar, PDF e papel. Não se compra de fornecedor e não se resolve com
modelo — é integração acumulada.

Também lê planilhas Excel (`services/importar_excel.py`) e texto colado.

---

## 6. Simulação por coortes

Quatro motores, não seis — `CRIA_RECRIA` usa o de cria, `RECRIA_ENGORDA` usa o
de engorda.

Cada um rastreia coortes etárias e fecha o balanço:

```
fim = início + nascimentos + compras − vendas − mortes
```

Quatro cenários: `conservador`, `crescimento`, `otimista`, `especulativo`. O
parecer usa o **conservador**.

A recria foi reescrita contra uma ficha real de 700 cabeças (§14).

---

## 7. Análise financeira

**Fluxo de caixa GEP Araguaia** — inclui **variação de estoque do rebanho**, o
valor criado pelo crescimento do plantel. Nenhum sistema de crédito rural
concorrente calcula isso automaticamente.

**DSCR em todos os anos do prazo.** O DSCR do ano 1 sozinho engana: o primeiro
ano liquida o estoque de animais prontos declarado na ficha; os seguintes vendem
só a produção corrente. Um ciclo completo chegou a projetar 6,08 no ano 1 e
−0,53 no ano 2 — e o parecer aprovava um crédito de 36 meses. Hoje a
recomendação segue o **ano crítico**.

**Política de crédito** (ajustável, não é benchmark zootécnico):

| Parâmetro | Valor |
|---|---|
| DSCR para aprovar | ≥ 1,30 |
| DSCR para ressalva | ≥ 1,00 |
| LTV folgado | ≤ 60% |
| LTV ajustado | ≤ 80% |
| Comprometimento de renda | ≤ 70% |

**Crédito máximo** por inversão do DSCR alvo. **Sensibilidade** a preço
(−15%/base/+15%) e a custo. **Breakeven** e **COE** contra referência Campo
Futuro/CNA.

**Custos por modalidade** — cria R$ 90,88/cab·mês contra ciclo completo
R$ 119,14.

### Endividamento total — `services/endividamento.py`

Inventário por credor: instituição, saldo devedor, parcela. O campo único antigo
continua funcionando e passa a se declarar **não discriminado**. O
comprometimento soma a parcela do crédito em análise, porque a decisão é sobre a
situação *depois* da operação.

Ausência declarada dispara aviso para conferir o **SCR do Banco Central** — zero
declarado pode ser verdade ou omissão, e o parecer não trata os dois igual.

### Garantia pelo valor de execução — `services/garantia.py`

Rebanho em penhor não se realiza pela cotação do dia: entre a inadimplência e o
caixa há apreensão, transporte, risco sanitário e venda forçada.

| Categoria | Deságio | Por quê |
|---|---|---|
| Boi (25m+) | 25% | cotação pública, vende na semana |
| Garrote (13–24m) | 35% | falta terminação |
| Matriz | 35% | valor depende da vida reprodutiva restante |
| Novilha (13–24m) | 40% | ainda não pariu |
| Bezerro/a (0–12m) | 50% | dois anos até terminação, maior mortalidade |

O deságio médio acompanha a composição. O LTV é medido sobre o valor de
execução, não sobre o de mercado.

### Rebaixamento

Capacidade de pagamento, garantia, endividamento e consistência são perguntas
independentes — vale a **pior** das respostas. Cada motivo entra na memória de
cálculo mesmo quando a recomendação já caiu por outro: o comitê precisa ver
todos os problemas, não só o primeiro que disparou.

---

## 8. Auditoria — onde os concorrentes não vão

**Reconciliação de garantia** (`services/reconciliacao.py`): cruza Imposto de
Renda × GTA × ficha sanitária e detecta rebanho de papel maior que o físico. O
caso real coberto por teste é **45.361 declarados contra 9.433 na ficha**.

**Consistência do rebanho** (`services/consistencia_rebanho.py`): detecta
incoerências na composição declarada, estima compra de animais implícita, e
rebaixa a recomendação quando encontra erro.

**Consistência histórica**: compara declarações da mesma fazenda ao longo do
tempo.

**Desfrute contra a própria referência**, com teto por modalidade:

| Ciclo | Teto |
|---|---|
| CRIA | 30% |
| CICLO_COMPLETO | 40% |
| CRIA_RECRIA | 40% |
| RECRIA | 55% |
| RECRIA_ENGORDA | 85% |
| ENGORDA | 120% |

Essa guarda já pegou um bug do **nosso próprio simulador** (§14).

**Memória de cálculo** em todo resultado — passo, valor e explicação. É o que
torna o parecer defensável diante do comitê e do BACEN, onde um score opaco não
é.

---

## 9. Preço por praça — `services/precos_regionais.py`

O indicador CEPEA/ESALQ é praça de São Paulo. O sistema aplicava o mesmo preço
no Brasil inteiro.

Informado o município, o diferencial da UF é aplicado **uma vez**, no ponto onde
os preços são resolvidos, e propaga para valoração, receita, fluxo, breakeven,
sensibilidade e garantia.

Mesmo rebanho, mesmo crédito de R$ 1,5 milhão:

| Praça | Basis | Garantia | LTV | Veredito |
|---|---|---|---|---|
| SP | 0% | 2.070.802 | 72,4% | ajustada |
| GO | −4% | 1.987.970 | 75,5% | ajustada |
| MT | −7% | 1.925.846 | 77,9% | ajustada |
| RO | −10% | 1.863.722 | 80,5% | **insuficiente** |

> **Origem dos diferenciais:** são calibração de referência, **não medição
> nossa**. O parecer, a tela e o PDF declaram isso por escrito. Limitação
> conhecida: o mercado de reposição é mais segmentado regionalmente que o de boi
> gordo, então o diferencial verdadeiro do bezerro costuma ser maior — aplicamos
> o mesmo fator por ora.

**Cotações**: scraper diário agendado (CEPEA/ESALQ para boi e bezerro, Scot para
vaca), com faixas de sanidade que rejeitam valor absurdo, e fallback para a
última cotação salva.

---

## 10. O loop de dado real

Todo o treino é sintético. O **botão de confirmação de ciclo** é o único caminho
por onde entra rótulo humano: o analista confirma a modalidade classificada ou
aponta a correta entre as seis.

O invariante, coberto por teste: o retreino consome **exclusivamente**
`class_conf`. Registro não confirmado não entra — o modelo nunca aprende com a
própria previsão.

A correção vale mais que a confirmação: é ela que mostra onde a faixa de
referência está errada.

---

## 11. IA e canais

**Narrativa e chat** (`services/groq_narrativa.py`) — Groq / Llama 3.3 70B.
Gera a leitura em prosa do parecer e responde perguntas sobre ele. Assíncrono
por padrão, para não somar 20s de latência à análise.

**WhatsApp** (`services/whatsapp.py`) — o mesmo chat, no canal onde o analista
já está.

A regra que impede vazamento: o webhook recebe um telefone e nada mais. Sem
vínculo explícito, responder sobre um parecer entregaria dado de crédito a quem
descobrisse o número do bot. O vínculo exige um código de uso único, 15 minutos
de validade, gerado por um analista **logado**. Número desconhecido não faz o
modelo ser nem consultado.

Autenticidade por HMAC-SHA256 em cada POST. Sem `WHATSAPP_APP_SECRET` a
requisição é **recusada**, não aceita — segredo ausente não vira "aceita tudo".

Detalhes que quebrariam em produção e estão cobertos: o **nono dígito** (a Meta
entrega celular brasileiro sem ele, o usuário digita com), recibos de leitura
que gerariam laço, e o 200 obrigatório em falha para a Meta não reenviar.

> **Não exercitado contra a API real da Meta** — falta credencial.

---

## 12. Produto

- Multiusuário com **empresas/consultorias** e vínculo N:N
- **Histórico por fazenda**, com pareceres anteriores para download
- **PDF do parecer** com logo e nome da consultoria
- Importação de Excel, PDF e texto colado; template para download
- Simulador de cenários interativo
- Cadastro, login, recuperação de senha por e-mail
- Painel administrativo
- Cotações e notícias do setor por RSS

---

## 13. Infraestrutura

**Banco:** PostgreSQL em produção, SQLite local — mesma camada de acesso.

Tabelas: `usuarios`, `fazendas`, `registros`, `pareceres`, `empresas`,
`empresa_membros`, `cotacao_arroba`, `meta`, `reset_tokens`,
`whatsapp_vinculos`, `whatsapp_codigos`.

**Deploy:** Docker, `python:3.11.15`, gunicorn 1 worker, timeout 120s. `libgomp1`
instalado — LightGBM e XGBoost o carregam por `ctypes` em runtime e a imagem
`-slim` não o traz; sem ele o app não sobe.

**Dependências fixadas em `==`.** Com faixas `>=`, cada rebuild montava um
ambiente diferente sem que uma linha de código mudasse — e o modelo é um pickle,
que não atravessa versão de biblioteca.

### Variáveis de ambiente

| Variável | Efeito |
|---|---|
| `DATABASE_URL` | PostgreSQL; ausente = SQLite |
| `SECRET_KEY` | sessão Flask |
| `GROQ_API_KEY` | liga narrativa e chat IA |
| `NARRATIVA_INLINE` | `1` volta a narrativa a ser bloqueante |
| `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` | ligam o canal; ausentes = rota 404 |
| `WHATSAPP_APP_SECRET` | **obrigatória** com o canal ligado |
| `WHATSAPP_VERIFY_TOKEN` | handshake de cadastro na Meta |
| `SHAP_AGRUPAR_REDUNDANTES` | `0` volta a listar features duplicadas |
| `REPOSICAO_PRECIFICADA` | `0` deixa de cobrar a compra de reposição |
| `FRAC_VENDA_RECRIA_M` | fração dos machos 13–24m vendidos (default 0,83) |
| `SMTP_*` | envio de e-mail |
| `ADMIN_EMAILS`, `ADMIN_SENHA_INICIAL` | administradores |

---

## 14. Testes — 417 casos

Os mais significativos:

| Arquivo | Casos | Cobre |
|---|---|---|
| `test_whatsapp` + `_rotas` | 52 | assinatura HMAC, vazamento, nono dígito |
| `test_precos_regionais` + ponta a ponta | 40 | praça atravessando a cadeia |
| `test_pdf_parsers` | 24 | as sete agências |
| `test_conservacao_seis_ciclos` | 20 | balanço de animais nas seis |
| `test_ml_engine` | 18 | classificação e simulação |
| `test_casos_material_treinamento` | 15 | fichas do material de referência |
| `test_garantia` + `test_endividamento` | 25 | deságio, LTV, comprometimento |
| `test_ficha_recria_real` | 11 | **a única validação não-sintética** |
| `test_regressao_bugs` | 10 | bugs que não podem voltar |

### A ficha real de recria

Uma ficha de 700 cabeças com composição, destino declarado e projeção de venda
foi a primeira validação não-sintética do projeto — e pegou um bug grande.

O simulador tratava 5–25 meses como pool único e vendia **100% dele todo ano**,
incluindo os de 5–12 meses recém-entrados, precificados pelo peso de **saída** da
recria. Tudo fora dessa faixa nunca era vendido.

| | Vendas | Machos | Fêmeas | Desfrute |
|---|---|---|---|---|
| Antes | 443 | 443 | **0** | 63,3% |
| Agora | 304 | 203 | 101 | 43,4% |
| **Ficha** | **315** | **211** | **104** | **45%** |

Receita estava ~41% superestimada. A guarda de desfrute acusou `63,3% > 55`
**sozinha**, antes de qualquer investigação.

A ficha levou a mais dois vazamentos: o motor de engorda deixava `va[8]` (fêmeas
acima de 36 meses) fora dos dois baldes de contabilização e elas sumiam do
modelo; o de cria contava a mortalidade das matrizes mas não a descontava do
fechamento.

---

## 15. O que está em aberto

Lista honesta, em ordem de impacto.

### Bug conhecido, não corrigido

**Carência não capitaliza juros.** A parcela é calculada sobre `prazo − carência`
sem crescer o principal pelos juros acumulados no período. Num crédito de
R$ 1 milhão, 36 meses, 12 de carência a 12,5% a.a.:

| | Parcela |
|---|---|
| Hoje | R$ 46.997 |
| Correto | R$ 52.872 |

**12,5% subestimada**, e o DSCR sobe na mesma proporção. Erra para o lado de
aprovar. Carência é padrão em custeio pecuário.

### Inconsistências

- **Sensibilidade usa DSCR do ano 1**, enquanto a conclusão usa o ano crítico.
  Na mesma tela, o veredicto grande e os cards de cenário usam bases diferentes.
- **`CICLO_COMPLETO`** tem desvio de balanço de −14 em 700 cabeças, no limite da
  tolerância de 2%. É o único motor não revisado.
- **`_build_model()` ramifica em `DATABASE_URL`** (100 árvores em produção, 300
  em dev). Hoje é inofensivo porque produção carrega o pickle; vira armadilha se
  o pickle falhar.

### Não validado

- **`CRIA_RECRIA`** segue sem validação (`xfail` em
  `test_casos_material_treinamento.py`)
- **Desfrute acima do teto** em CRIA (43% vs 30), CICLO_COMPLETO (41,7% vs 40) e
  CRIA_RECRIA (49% vs 40) com rebanhos **sintéticos construídos para auditoria**.
  Pode ser bug, pode ser rebanho mal construído — só uma ficha real resolve.
- **`_FRAC_VENDA_RECRIA_M = 0,83`** vem de **uma** ficha
- **WhatsApp** nunca exercitado contra a API real da Meta
- **Diferenciais regionais de preço** são calibração, não medição

### Ausente

Do roteiro padrão dos 5 C's de crédito, dois seguem descobertos:

- **Caráter** — sem consulta a Serasa, SPC, CADIN, protestos ou ações judiciais
- **Capital** — sem balanço nem patrimônio líquido; o endividamento é
  **declarado**, não verificado no SCR

---

## 16. Onde o projeto é único

Comparado às plataformas de crédito agro estabelecidas, que são **grão-primeiro
e produtor-primeiro**:

1. **Lê o rebanho.** Sensoriamento remoto e NDVI demarcam área de safra — não
   contam cabeça, não dizem idade nem sexo. Para pecuária, a garantia é viva e
   se move.
2. **Sete agências estaduais parseadas.** Trabalho sujo, acumulado, sem atalho.
3. **Audita a garantia.** Rebanho de papel contra rebanho físico é uma pergunta
   que a arquitetura deles não faz.
4. **É auditável.** Memória de cálculo linha por linha, onde um score de 100+
   fontes é caixa-preta — e a Res. CMN 4.966 exige que a instituição justifique.

O ativo que ainda falta construir e que composto vira fosso: **série histórica de
GTA**. Hoje lemos a GTA, extraímos o saldo e descartamos o resto. Cada GTA é um
registro datado de movimentação; guardadas, dão trajetória documentada em vez de
declarada, desfrute medido em vez de estimado, e benchmarks reais no lugar das
faixas sintéticas.
