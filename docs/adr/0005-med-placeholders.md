# ADR 0005 — Simulação do ciclo de contestação (MED) sem afirmar regras oficiais

**Status:** aceita · 2026-10-20

## Contexto
O ciclo de contestação de Pix tem regras e prazos definidos pelo Banco Central. Este repositório não consultou nem reproduz a norma, e não tem integração com SPI/DICT.

## Decisão
- `med.py` modela uma máquina de estados **didática** (`CREATED → AUTHORIZED → SETTLED → FLAGGED → CAUTIONARY_BLOCK → MED_OPENED → ANALYSIS → RETURNED/REJECTED → CLOSED`), com transições válidas explícitas e erro para qualquer outra.
- Os prazos (`MedConfig`) são **placeholders ilustrativos** (`is_placeholder = True`), a confirmar na documentação oficial antes de qualquer uso que dependa deles.
- O README e o relatório carregam o aviso: *simulação educacional baseada em documentação pública; sem integração com SPI/DICT e sem operação bancária real*.

## Consequências
- Nenhuma afirmação sobre prazos legais é feita.
- Fase F6 do roadmap: conferir fonte oficial e substituir os placeholders citando o documento.
