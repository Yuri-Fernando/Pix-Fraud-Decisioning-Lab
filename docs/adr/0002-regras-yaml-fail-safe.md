# ADR 0002 — Regras em YAML versionado e motor fail-safe

**Status:** aceita · 2026-10-20

## Contexto
Regras antifraude precisam ser auditáveis, ajustáveis por limiar e explicar cada decisão.

## Decisão
- Regras em `rules/rules_v1.yaml` com `id`, `action` (`REVIEW|BLOCK`), `weight`, `reason_code`, `params` e condição `all/any` sobre features gold. Parâmetros são referenciados por `"$nome"` e podem ser sobrescritos em memória (`with_params`) para varredura de limiar sem editar o arquivo.
- A ação mais severa entre as regras disparadas define a decisão; o `rule_score` é `1 − Π(1 − peso)`.
- **Fail-safe:** qualquer erro do motor (feature ausente, operador desconhecido) ⇒ `REVIEW` com `ENGINE_ERROR`, nunca `APPROVE`. Valores `NaN` simplesmente não satisfazem a condição.
- Definições inválidas (ação fora do conjunto, peso fora de [0,1], IDs duplicados, campo ausente) são rejeitadas no carregamento.

## Consequências
- Cada decisão carrega `reason_codes` e `evidence` (valores das features usadas pelas regras disparadas).
- Pesos são **hipóteses** de partida, não calibrados com dados reais.
- A versão do conjunto (`version`) acompanha o relatório.
