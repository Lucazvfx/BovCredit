# BovCredit — Plataforma de Análise de Crédito Pecuário

> **Emita pareceres de crédito rural com metodologia, Machine Learning e PDF com a marca da sua consultoria — em minutos.**

Sistema especializado em análise técnico-financeira de rebanho bovino para **consultorias de crédito rural**. A plataforma classifica automaticamente o tipo de exploração (Cria / Recria / Engorda / Ciclo Completo), projeta a geração de caixa com metodologia, audita a consistência do rebanho declarado e emite um **parecer de crédito com recomendação Aprovar / Ressalva / Negar** baseado no DSCR — tudo em uma única tela.

---

## Screenshots

**Landing page**
![Landing page](docs/screenshots/landing.png)

**Inserir dados do rebanho**
![Inserir dados](docs/screenshots/app_inserir.png)

**Simular Cenários — Dashboard**
![Simular Cenários Dashboard](docs/screenshots/simular_dashboard.png)

---

## Por que usar esta plataforma?

| Problema da consultoria hoje | O que a plataforma resolve |
|---|---|
| Análise feita em planilha, demorada e propensa a erro | Resultado completo em menos de 1 minuto |
| Sem metodologia padronizada entre os analistas | Metodologia padronizada aplicada de forma uniforme |
| Rebanho declarado sem auditoria | Score de consistência + flags automáticos de inconsistência |
| PDF genérico sem identidade da empresa | PDF com logo e nome da consultoria em cada parecer |
| Sem histórico das fazendas analisadas | Histórico completo por fazenda com download de pareceres anteriores |
| Cotações desatualizadas | Preços da arroba atualizados automaticamente todo dia às 8h (CEPEA/Scot) |

---

## Funcionalidades principais

### Análise técnica do rebanho
- **Classificação ML automática** do ciclo de produção: Cria / Recria / Engorda / Ciclo Completo via ensemble de ML com ~99,8% de acurácia
- **Importação de PDFs** de órgãos estaduais de defesa agropecuária e GTA — extrai a composição do rebanho automaticamente
- **Indicadores zootécnicos** calculados na hora: relação F/M, % matrizes, pirâmide etária, bezerros estimados
- **Benchmarks nacionais e regionais** (CEPEA, Embrapa, ABCZ, Scot, ASBIA, Inttegra)
- **Score de consistência 0–100** com flags de erros: pirâmide invertida, touro impossível, crescimento implausível, categorias desaparecidas

### Financeiro e crédito
- **Fluxo de caixa pecuário**: resultado operacional (caixa) + variação de estoque do rebanho = resultado econômico total
- **Parecer de crédito com DSCR**, parcela Price e recomendação fundamentada
- **Análise de sensibilidade de preço**: 3 cenários automáticos (−15% / base / +15%) — mostra se o crédito sobrevive a uma queda no boi
- **Capacidade máxima de endividamento**: quanto o produtor pode tomar dado o DSCR-alvo
- **Projeção financeira de 5 anos** em 4 cenários (otimista, crescimento, alta venda, conservador)
- **Reconciliação de garantia**: cruza ficha sanitária × IR × GTA para detectar rebanho superavaliado

### Para a consultoria
- **Multiempresa**: cada consultoria tem seus dados isolados; analistas compartilham clientes dentro da mesma empresa
- **PDF com marca própria**: logo e nome da consultoria no cabeçalho de cada parecer exportado
- **Histórico de pareceres** por fazenda com download em PDF
- **Retreino do modelo ML** com confirmações dos analistas — o modelo melhora com o uso

---

## Como funciona (fluxo em 3 passos)

```
1. INSERIR DADOS
   ├── Fazenda, proprietário, município
   ├── Composição do rebanho (manual / upload de PDF / planilha Excel)
   ├── Solicitação de crédito (valor, prazo, juros, carência)
   └── Cotações do dia (preenchidas automaticamente)

2. CLASSIFICAR
   ├── ML classifica o ciclo de produção
   ├── Calcula indicadores, benchmarks e consistência
   ├── Gera fluxo de caixa + valoração do rebanho
   └── Emite parecer com DSCR, 3 cenários de sensibilidade de preço

3. RESULTADO
   ├── Banner APROVAR / RESSALVA / NEGAR em destaque
   ├── KPIs: DSCR, parcela/mês, geração de caixa/ano, crédito máximo
   ├── Fluxo de caixa com variação de estoque
   ├── Benchmarks, pirâmide etária, indicadores, recomendações
   └── Exportar PDF com marca da consultoria
```

---

## Faixas de recomendação de crédito

| DSCR | Recomendação | Significado |
|---|---|---|
| ≥ 1,30 | **APROVAR** | Produtor gera 30% mais caixa do que precisa para pagar a dívida |
| 1,00 a 1,29 | **APROVAR COM RESSALVA** | Cobre o serviço da dívida com folga estreita |
| < 1,00 | **NEGAR** | Geração de caixa insuficiente |

---

## Metodologia — Fluxo de Caixa

A plataforma implementa uma metodologia de fluxo de caixa para pecuária de corte, diferencial que nenhum sistema de crédito rural mainstream oferece:

```
(+) Receita de vendas
(−) Custo operacional
(−) Reposição de reprodutores
(=) RESULTADO OPERACIONAL ← base do DSCR (caixa real disponível para pagar a dívida)

(±) Variação de estoque do rebanho
(=) RESULTADO ECONÔMICO TOTAL ← riqueza criada (caixa + patrimônio)

(−) Serviço da dívida anual
(=) FLUXO LIVRE
```

### Pesos e rendimentos por categoria

| Categoria | Arrobas-eq | Rendimento | Referência de preço |
|---|---|---|---|
| Boi adulto | 20,53@ | 55% RC | preco_boi |
| Vaca/Matriz | 15,33@ | 50% RC | preco_vaca |
| Garrote 13–24m | 10,67@ | 50% RC | média boi+vaca |
| Novilha 13–24m | 9,33@ | 50% RC | média boi+vaca |
| Bezerro 0–12m | 6,67@ | 50% RC | preco_bezerro (R$/cab) |
| Bezerra 0–12m | 6,00@ | 50% RC | preco_bezerra (R$/cab) |

---

## Classificação por Machine Learning

### Entrada
Vetor de 10 valores representando a composição do rebanho por faixa etária e sexo:

```
v = [fêmeas 00–04m, machos 00–04m,
     fêmeas 05–12m, machos 05–12m,
     fêmeas 13–24m, machos 13–24m,
     fêmeas 25–36m, machos 25–36m,
     fêmeas adultas, machos adultos]
```

### Saída

| Classe | Tipo | Característica |
|---|---|---|
| 0 | **CRIA** | Predomínio de matrizes; produção de bezerros |
| 1 | **RECRIA** | Alta concentração 13–24m; desenvolvimento pós-desmame |
| 2 | **ENGORDA** | Machos adultos dominam; terminação para abate |
| 3 | **CICLO_COMPLETO** | Todas as fases integradas na mesma propriedade |

### Modelo
Ensemble **VotingClassifier** (soft voting):
- `RandomForestClassifier` (100 estimadores)
- `GradientBoostingClassifier`
- `XGBClassifier`
- `MLPClassifier` — rede neural 2 camadas ocultas

**Acurácia típica: ~99,8%** sobre dataset de 3.902 amostras. O modelo melhora automaticamente a cada confirmação de analista.

---

## Consistência do Rebanho

Score de auditoria lógica de 0–100 com flags automáticos:

| Flag | Tipo | Critério |
|---|---|---|
| Pirâmide invertida | Erro | Bezerros > adultos × fator esperado |
| Touro impossível | Erro | Sem bois com muitas matrizes |
| Matrizes sem bezerros | Alerta | Matrizes adultas mas zero bezerros |
| Relação F/M anômala | Alerta | Proporção fora de padrão por ciclo |
| Crescimento implausível | Erro | Rebanho cresceu > 200% em 12 meses |
| Categoria desaparecida | Alerta | Categoria com > 50 cabeças sumiu no histórico |

> Se houver erros e a recomendação seria Aprovar, o sistema rebaixa automaticamente para Ressalva com justificativa.

---

## Análise de Sensibilidade de Preço

3 cenários automáticos após cada análise:

| Cenário | Fator | Uso |
|---|---|---|
| ▼ Queda 15% | 0,85 × preço base | Mostra se o crédito sobrevive a uma queda do boi |
| ● Base | 1,00 × preço base | Cotação do dia |
| ▲ Alta 15% | 1,15 × preço base | Cenário favorável |

---

## Reconciliação de Garantia

Cruza rebanho declarado em diferentes documentos para detectar superavaliação:

| Documento | Representa |
|---|---|
| Ficha Sanitária (órgão estadual) | Piso físico — animais vacinados, não pode ser forjado |
| Imposto de Renda | Declaração à Receita Federal |
| GTA | Movimentações recentes |

---

## Projeção 5 Anos — 4 Cenários

| Cenário | Estratégia |
|---|---|
| Otimista | IATF, suplementação, genética melhorada |
| Crescimento Gradual | Expansão sustentável com reinvestimento |
| Alta Venda | Maximiza venda aproveitando preço favorável |
| Conservador | Manutenção mínima — cenário de queda de preços |

---

## Cotações Automáticas

| Preço | Fonte | Frequência |
|---|---|---|
| Boi gordo (R$/@) | CEPEA/ESALQ via Notícias Agrícolas | Diária às 8h |
| Vaca gorda (R$/@) | Scot Consultoria | Diária às 8h |
| Bezerro/Bezerra | Referência editável | Manual |

---

## Importação de Dados

### PDFs suportados

| Documento | Estado | Parser |
|---|---|---|
| Saldo Atual da Exploração | Mato Grosso | `parsers/indea.py` |
| Declaração de Existência | Rondônia | `parsers/idaron.py` |
| GTA / Ficha de Declaração | Rondônia | `pdf_parsers.py` |

Múltiplos PDFs podem ser enviados de uma vez — o sistema soma os rebanhos automaticamente.

### Planilha Excel
Template disponível para download em `/api/template/download`.

---

## Tecnologia e Arquitetura

### Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.10 + Flask |
| ML | scikit-learn, XGBoost, LightGBM |
| Banco | PostgreSQL (produção) / SQLite (desenvolvimento) |
| PDF geração | reportlab |
| PDF leitura | pdfplumber |
| Frontend | HTML/CSS/JS (sem framework) |
| Scheduler | APScheduler |
| Deploy | Railway (auto-deploy via push em `main`) |

### Estrutura de arquivos

```
app.py                        # Flask — rotas, auth, scheduler
ml_engine.py                  # Ensemble ML + simulações financeiras
database.py                   # Abstração SQLite/PostgreSQL
scraper.py                    # Cotações diárias (CEPEA/Scot)
pdf_parsers.py                # Parser de PDFs (órgãos estaduais/GTA)

services/
  fluxo_caixa_gep.py          # Valoração + DRE
  parecer_credito.py          # Price, DSCR, crédito máximo
  parecer_pdf.py              # Geração de PDF (reportlab)
  consistencia_rebanho.py     # Score de consistência + flags
  parametros_zootecnicos.py   # Benchmarks por ciclo
  custos_desembolso.py        # Presets de custo por componente
  pesos_rebanho.py            # Conversão cabeças → arrobas
  benchmarks_nacionais.py     # Benchmarks multifonte
  reconciliacao.py            # Reconciliação de documentos

parsers/
  indea.py                    # Parser MT
  idaron.py                   # Parser RO

templates/
  index.html                  # SPA principal
  admin.html                  # Gestão de empresas e usuários
  login.html / cadastro.html

tests/                        # pytest — 50+ arquivos de teste
```

---

## API Principal

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/classificar` | Classificar rebanho + gerar parecer completo |
| POST | `/api/cenario` | Projeção de cenário (Ciclo Completo) |
| GET | `/api/precos/live` | Cotações do dia |
| GET/POST | `/api/empresa/perfil` | Marca da consultoria (nome + logo) |
| POST | `/api/parecer/pdf` | Gerar PDF do parecer |
| GET | `/api/fazendas` | Listar fazendas da empresa ativa |
| POST | `/api/fazendas` | Criar fazenda |
| GET | `/api/fazendas/<id>/pareceres` | Histórico de pareceres |
| POST | `/api/ler-pdf` | Extrair composição de PDF |
| GET | `/api/template/download` | Template Excel |
| POST | `/api/confirmar` | Confirmar/corrigir classificação ML |
| POST | `/api/reconciliar` | Reconciliar documentos de garantia |

### Exemplo: classificar e obter parecer

```python
import requests

r = requests.post('http://localhost:5050/api/classificar', json={
    # Composição: [f00F, f00M, f05F, f05M, f13F, f13M, f25F, f25M, facF, facM]
    'valores': [300, 280, 400, 200, 900, 1200, 250, 80, 600, 40],

    # Cotações
    'preco_boi': 330,
    'preco_vaca': 260,
    'preco_bezerro': 1800,
    'preco_bezerra': 1620,

    # Crédito solicitado
    'credito_valor': 500000,
    'prazo_meses': 24,
    'juros_aa': 0.10,
    'carencia_meses': 0,
    'dividas_mensais': 0,

    # Identificação
    'fazenda': 'Fazenda Modelo',
    'municipio': 'Sinop - MT',
    'proprietario': 'João da Silva',
})
p = r.json()

print(p['classificacao'])                              # CICLO_COMPLETO
print(p['parecer']['conclusao']['recomendacao'])       # aprovar
print(p['parecer']['conclusao']['dscr'])               # ex.: 1.45
print(p['parecer']['conclusao']['capacidade_maxima'])  # crédito máximo (R$)
print(p['fluxo_gep']['resultado_operacional'])         # geração de caixa anual
print(p['sensibilidade'])                              # 3 cenários de preço
```

---

## Parâmetros de referência

### Zootécnicos (fontes: Embrapa, ABCZ, Scot, CEPEA)

| Parâmetro | Valor default | Fonte |
|---|---|---|
| Taxa de natalidade | 65% | Embrapa/Scot/CEPEA/ABCZ |
| Mortalidade geral | 3% | Referência setorial |
| Taxa de desmama | 82% | Referência setorial |
| Rendimento de carcaça | 52% | Referência setorial |
| Proporção boi/matriz | 1:30 | Ciclo Completo padrão |
| Renovação de bois | 20%/ano | Mercado |
| Descarte de matrizes | 30%/ano | Mercado |
| Peso boi adulto | 18–20@ | CEPEA/B3 |
| Peso vaca descarte | 14–15@ | Mercado MT/RO |

### Política de crédito

| Parâmetro | Valor |
|---|---|
| DSCR mínimo para aprovar | 1,30 |
| DSCR mínimo para ressalva | 1,00 |
| DSCR-alvo para crédito máximo | 1,30 |

---

## Instalação e Deploy

### Rodando localmente

```bash
pip install -r requirements.txt
python app.py
# Acesse: http://localhost:5050
```

Crie uma conta em `/cadastro` e faça login. Na primeira execução o modelo ML é treinado automaticamente (alguns segundos).

### Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `DATABASE_URL` | URL PostgreSQL. Sem ela, usa SQLite local. |
| `SECRET_KEY` | Chave de sessão Flask (obrigatória em produção). |
| `ADMIN_EMAILS` | E-mails de admin separados por vírgula. |
| `ADMIN_SENHA_INICIAL` | Senha inicial dos admins (opcional). |

### Deploy Railway

Push em `main` dispara deploy automático:

```bash
git push origin main
```

---

## Testes

```bash
# Rodar todos os testes
python -m pytest tests/ -v

# Ignorar testes que precisam de arquivos locais
python -m pytest tests/ -v \
  --ignore=tests/test_pdf_reais_indea.py \
  --ignore=tests/test_csrf_e_limiter.py \
  --ignore=tests/test_benchmarks_reais.py
```

---

## Multiempresa e Multiusuário

```
Consultoria A
├── Analista 1 (admin)
├── Analista 2
└── Fazendas: [Fazenda Norte, Fazenda Sul]

Consultoria B
├── Analista 3
└── Fazendas: [Fazenda Leste]
```

- Isolamento total entre consultorias
- Um usuário pode ser membro de múltiplas empresas
- Painel `/admin` para gestão de empresas, membros e permissões
- Logo e nome da consultoria configuráveis por empresa (aparecem no PDF)

---

## Licença

© 2026 Lucas Vinicius. Todos os direitos reservados.

Protegido pela **Lei 9.610/98 (Direitos Autorais)** e **Lei 9.609/98 (Software)**.

É vedado copiar, modificar, distribuir ou sublicenciar este software sem autorização prévia por escrito.

**Licenciamento comercial:** viniciuslukas353@gmail.com
