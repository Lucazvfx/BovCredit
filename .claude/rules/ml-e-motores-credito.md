---
paths: ["ml_engine.py", "treinar_ciclos.py", "services/parecer_credito.py", "services/rating_credito.py", "services/checklist_credito.py", "services/benchmarks_nacionais.py", "services/*_engine/**"]
---

# ML e motores de crédito

Complementa o CLAUDE.md. Só o que evita regressão.

- **SHAP fica fora do caminho síncrono.** `/api/classificar` retorna `shap_pendente=true` e o
  frontend busca `/api/shap` depois (pico de ~460 MB). Não chame `explicar_shap` dentro de
  `classificar`/`calcular_indicadores` nem em rota síncrona; `SHAP_INLINE=1` é só opt-in.
  Teste de guarda: `tests/test_shap_assincrono.py`.
- **`gestao_model.pkl` (~300 MB RSS)** é carregado uma vez no master (`preload_app`). Não
  carregue o modelo por request nem em import de módulo auxiliar; evite novas cópias grandes em memória.
- **Versões ML travadas** (scikit-learn 1.5.2, numpy 1.26.4): mudar qualquer dependência ML
  em `requirements.txt` exige `python treinar_ciclos.py` e commitar o `.pkl` regerado.
  Mudar features, `TIPOS` ou `PARAMS_POR_CICLO` também invalida o pickle atual.
- **Mudou regra de risco, parecer, caixa ou estresse?** Revalide: rode a suíte inteira
  (`python -m pytest`), em especial os testes de motores, parecer e casos de treinamento, e confira que
  rating, checklist, DSCR/capacidade de pagamento e cenários de estresse continuam coerentes
  entre si no parecer final. Quando a regra reverter a decisão do modelo, mantenha
  `origem_decisao`/`regra_aplicada` preenchidos (rastreabilidade).
- **Não "consertar" um teste de domínio ajustando o número esperado** sem entender por que a
  saída mudou; uma mudança de resultado é decisão de crédito, não detalhe de implementação.
