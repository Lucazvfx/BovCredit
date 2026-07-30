# Como reverter as mudanças

Todas as alterações recentes são controladas por variável de ambiente ou
isoladas em arquivos próprios. Nenhuma exige alterar código para desligar.

## Por variável de ambiente (sem deploy, efeito imediato)

Defina no Railway → Variables. O app volta ao comportamento anterior no
próximo restart.

| Variável | Padrão | Para reverter | O que faz |
|---|---|---|---|
| `GROQ_API_KEY` | ausente | **remover** | Desliga narrativa IA e chat. Sem ela, tudo funciona como antes. |
| `NARRATIVA_INLINE` | `0` | `1` | Volta a gerar a narrativa dentro de `/api/classificar` (bloqueante, até 20s mais lento). |
| `SHAP_AGRUPAR_REDUNDANTES` | `1` | `0` | Volta o SHAP a listar as 40 features separadas, com duplicatas. |
| `REPOSICAO_PRECIFICADA` | `1` | `0` | Deixa de cobrar a compra de reposição 1:1 em recria/engorda. A compra continua no balanço de animais, mas volta a custar zero — o DSCR dessas operações sobe ~4×. |

## Por reversão de commit

Cada mudança é um commit isolado. Para desfazer uma sem tocar nas outras:

```bash
git revert <hash>
```

| Commit | O que introduziu |
|---|---|
| `33fdc09` | Narrativa IA via Groq (feature flag) |
| `9ff4745` | Chat com o parecer |
| `e389f14` | Correção do SHAP + proveniência da decisão + atipicidade |
| *(este)* | Narrativa assíncrona + agrupamento de features no SHAP |

## Por remoção de arquivo

Estes arquivos são autocontidos — apagá-los remove o recurso inteiro:

- `services/groq_narrativa.py` — narrativa e chat IA
  (remover também o import e as rotas `/api/chat` e `/api/narrativa` em `app.py`)

## O que NÃO é revertível por flag

Estas correções são de bugs; não há motivo para desligá-las, e voltar atrás
significa reintroduzir o defeito:

- **`abort` importado no `app.py`** — sem isso, a proteção CSRF de `/admin`
  devolve 500 em vez de 403.
- **`for est in voting.estimators_`** — o desempacotamento como tupla lançava
  `ValueError` em toda chamada e o SHAP nunca era gerado.

## Estado do modelo

O `gestao_model.pkl` **não foi retreinado** por nenhuma dessas mudanças. O
agrupamento do SHAP é apresentação, não modelagem — o modelo continua
recebendo as mesmas 40 features.

> **Atenção:** o `.pkl` está versionado no git e é carregado no boot. Se o
> arquivo faltar, o `app.py` treina do zero (>300s), o que estoura o
> `--timeout 120` do gunicorn e derruba o deploy. Não remova do versionamento
> sem antes criar um passo de build que gere o modelo.
