---
paths: ["app.py", "services/totp.py", "services/cripto_segredo.py", "services/groq_narrativa.py", "services/assistente.py", "templates/**"]
---

# Rotas, auth/2FA e UI

Complementa o CLAUDE.md. Só o que evita regressão.

- **Auth/2FA**: não enfraqueça `login_required`, verificação TOTP nem códigos de backup. O
  segredo 2FA é cifrado por `services/cripto_segredo.py`; nunca grave, logue ou devolva segredo
  em claro. Não troque `SECRET_KEY` sem antes fixar `TOTP_CHAVE` (senão todos perdem o 2FA).
- **Rate limits (`@limiter.limit`)**: rota nova de login, cadastro, upload, IA (Groq/assistente)
  ou memória pesada (`/api/shap`, `_LIM_MEMORIA`) deve ter limite. Não remova nem afrouxe os
  existentes para "fazer um teste passar".
- **Erros**: respostas ao cliente com mensagem genérica; detalhe (traceback, SQL, caminho,
  resposta do Groq) só no log. Nunca `str(e)` direto no JSON. Ver `tests/test_erros_visiveis.py`.
- **Groq/assistente**: não envie ao provedor dados pessoais além do necessário; falha ou
  timeout do Groq não pode derrubar a análise (narrativa é complementar).
- **`templates/landing.html`**: preserve as 4 fases do scroll (formulário → classificação →
  DSCR → veredito), o container `position: sticky` de 500vh com progresso via
  `requestAnimationFrame`, e os tokens CSS com dark mode. Teste claro e escuro ao mexer em cor/layout.
- **`templates/index.html`**: não quebre os fluxos de análise, rascunho e parecer (ids, handlers
  e campos que o JS e as rotas esperam). Ao ajustar layout, mantenha nomes de campos/ids e
  escape de saída no frontend; confira `tests/test_acabamento_*`. Para mudanças de UI use a
  skill `orkavyn-ui`.
