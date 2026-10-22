# ADR 0003 — Detecção de grafo em micro-batch, com alerta retrospectivo

**Status:** aceita · 2026-10-20

## Contexto
Ciclos, cadeias de encaminhamento e hubs de mula só são visíveis depois que várias transações existem. Computar o grafo sobre todo o conjunto vazaria o futuro para transações antigas.

## Decisão
- A cada 10 minutos (passo) é construído o grafo das transações dos últimos 60 minutos; só roda se houve transação nova no passo.
- Padrões: `cycle` (ciclos simples de 3–4 nós; ida e volta entre dois nós é normal e fica de fora), `chain` (≥ 3 encaminhamentos em ≤ 10 min mantendo ≥ 80% do valor), `mule_hub` (≥ 5 remetentes distintos, ≥ 2 destinos e saída acumulada ≥ 70% do recebido em ≤ 15 min após a última entrada).
- Cada transação recebe `graph_flag_ts` = primeiro passo em que o padrão apareceu. Isso é um **alerta retrospectivo**: a transação pode já ter sido liquidada.

## Consequências
- Propriedade testada: alertas com `graph_flag_ts ≤ T` são idênticos quando os dados são cortados em T.
- O atraso mediano de detecção na execução de referência foi 659,5 s.
- Flags de grafo não entram no classificador (evita acoplar o ML a um sinal retrospectivo); entram na combinação final e nas regras GRAPH001/GRAPH002.
