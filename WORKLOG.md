# Worklog

Registro cronológico de decisões e do que foi realmente executado.

## 2026-10-20 — v0.1.0

**Ambiente verificado:** Python 3.10.8; pandas 2.2.3, NetworkX 3.4.2, scikit-learn 1.7.2, PyYAML 6.0.3, matplotlib 3.10.0. `pyspark` ausente; Java 1.8.0_491 (único). ⇒ backend Spark escrito e **não executado**.

**Decisões**
- Núcleo em pandas; Spark opcional (ADR 0001).
- Rótulos em tabela separada desde o gerador; teste de truncamento prova ausência de vazamento nas features.
- Grafo em micro-batch de 10 min com janela de 1 h; alerta retrospectivo com `graph_flag_ts` (ADR 0003).
- Decisão final com piso nas regras; ML sozinho não alcança `BLOCK` (`w_ml = 0,6 < 0,8`).
- LLM só escreve em `summary`; `UPDATE` em campos de decisão é abortado por *trigger* (ADR 0004).
- Prazos do MED são placeholders (`MedConfig.is_placeholder = True`) (ADR 0005).

**Execuções reais**
- `python -m pytest` ⇒ 88 passed, 1 skipped (paridade Spark: NOT_RUN).
- `python -m pixfraud run --out reports` (seed 42) ⇒ 8 536 transações, 292 fraudes; PR-AUC teste: ML 0,937 · regras 0,848 · combinado 0,975.
- Tempo ponta a ponta: ~100 s ⇒ ~58 s após otimizar o grafo e limitar threads do OpenMP; resultados idênticos.

**Achado:** a primeira geração de dados era fácil demais (toda conta nova era fraude). Foram adicionados contas legítimas recém-abertas, compras grandes legítimas e vaquinhas entre amigos, que passaram a produzir falsos positivos em PIX002, PIX003 e MULE001.

**Não verificado:** Linux/macOS, GitHub Actions, provider Claude contra a API real, backend Spark.
