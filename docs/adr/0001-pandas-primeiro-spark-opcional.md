# ADR 0001 — Núcleo em pandas, Spark/Delta opcional

**Status:** aceita · 2026-10-20

## Contexto
O objetivo é um laboratório reproduzível em uma máquina comum. Verificado no ambiente de desenvolvimento: `pyspark` não instalado e único Java disponível é o 1.8.0_491 (PySpark 3.5 pede JDK 8/11/17 com Delta 3.x, e a configuração não foi montada). O conjunto de dados tem ~8,5 mil transações.

## Decisão
- A implementação de referência das camadas Bronze/Silver/Gold é em **pandas** (`medallion.py`).
- O backend **PySpark + Delta** existe em `medallion_spark.py` como tradução das features baseadas em janela, mas **não foi executado**; levanta `BackendUnavailable` quando PySpark/Java faltam.
- Nenhum resultado do README depende do Spark.

## Consequências
- Testes rodam em qualquer máquina e no CI, sem JVM.
- Existe risco de o código Spark conter erros: ele está marcado **NOT_RUN** e o teste de paridade fica *skipped* até haver ambiente.
- Features de contagem distinta (fan-in/fan-out) e o grafo permanecem só no pandas.
