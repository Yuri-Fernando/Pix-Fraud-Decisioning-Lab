# ADR 0004 — LLM somente consultivo, com limites impostos por construção

**Status:** aceita · 2026-10-20

## Contexto
Resumos e hipóteses de investigação são úteis ao analista, mas um modelo de linguagem não deve decidir bloqueio de conta.

## Decisão
- Interface `CaseSummarizer`; padrão `DeterministicSummarizer` (template, sem rede). `ClaudeSummarizer` é opcional: chave apenas via `ANTHROPIC_API_KEY`, cliente injetável para teste, qualquer falha cai no resumo determinístico.
- O *system prompt* proíbe recomendar bloqueio como ordem e trata o conteúdo das evidências como dado.
- No SQLite, um **trigger** aborta qualquer `UPDATE` em `tx_id`, `decision`, `score`, `reasons` e `evidence`. A triagem escreve só em `summary`, `summary_provider` e `status`. Resultado do caso só por `resolve()` com `CONFIRMED_FRAUD | FALSE_POSITIVE` e nome do analista.
- O score final e a decisão não têm o LLM como entrada.

## Consequências
- Teste com um "resumidor malicioso" confirma que a decisão permanece intacta.
- O provider Claude foi testado apenas com cliente simulado; **não** foi executado contra a API real nesta revisão.
