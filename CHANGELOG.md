# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Versionamento semântico.

## [0.1.0] — 2026-10-20

### Adicionado
- Gerador de transações Pix/TED sintéticas reprodutível (seed), com 8 padrões de fraude (mula, fan-out, ciclo, cadeia/triangulação, velocity, novo favorecido, troca de dispositivo, anomalia de valor) e tráfego legítimo "difícil" (contas novas legítimas, compras grandes, vaquinha entre amigos). Rótulos em tabela separada.
- Camadas Bronze/Silver/Gold em pandas; quarentena com motivo; features *point-in-time*.
- Motor de regras YAML versionado (`rules_v1.yaml`, 11 regras) com *reason codes*, evidência, pesos, parâmetros por regra e fail-safe (`ENGINE_ERROR` ⇒ `REVIEW`).
- Análise de grafo com NetworkX: features de nó, ciclos, cadeias de encaminhamento, hubs de mula; detecção em micro-batch.
- Classificador `HistGradientBoosting` com split temporal e purga; combinação de sinais por *noisy-OR*.
- Simulador de estados Pix/MED com transições válidas e prazos placeholder.
- Monitor por regra e varredura de limiar (tabela e gráfico).
- Casos em SQLite com campos de decisão imutáveis e triagem consultiva (template determinístico; provider Claude opcional).
- Relatório Markdown/HTML/PNG, CLI (`run`, `sweep`, `med-demo`), CI (arquivo), Makefile.
- Backend PySpark + Delta **escrito, não executado** (`medallion_spark.py`).
- 88 testes (1 NOT_RUN).

### Corrigido durante o desenvolvimento
- Dados iniciais eram fáceis demais (toda conta nova era fraude); adicionado tráfego legítimo que gera falso positivo.
- Pipeline de ~100 s para ~58 s sem alterar resultados (grafo sem `groupby` do pandas; OpenMP limitado a 2 *threads*).
