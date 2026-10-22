# Roadmap

Legenda: ✅ concluído · 🟡 parcial · ⏳ planejado. Itens ⏳ são intenção, não funcionalidade existente.

| Fase | Escopo | Estado | Evidência / gate |
|---|---|---|---|
| F0 | Dados sintéticos, medalhão pandas, teste de vazamento | ✅ | `tests/test_generator_medallion.py` |
| F1 | Regras YAML, grafo, ML, combinação | ✅ | `tests/test_rules.py`, `test_graph.py`, `test_scoring_ml.py` |
| F2 | Simulador MED, monitor por regra, casos SQLite, triagem consultiva | ✅ | `tests/test_med_monitor.py`, `test_cases_llm.py` |
| F3 | Executar o backend Spark/Delta e comparar com o pandas | ⏳ | gate: teste de paridade das features em janela, rodando em JDK 11/17 + PySpark 3.5 |
| F4 | Ingestão em fluxo (Redpanda → Structured Streaming) | ⏳ | gate: latência medida por estágio |
| F5 | Grafo persistido (Neo4j) | ⏳ | gate: mesmas detecções do micro-batch com latência menor |
| F6 | Prazos/estados do MED conferidos na documentação oficial | ⏳ | gate: constantes deixam de ser placeholder, com link da fonte |
| F7 | Fraudes adversariais (padrões que as regras não conhecem) e calibração de pesos | ⏳ | gate: queda de recall mensurada e recuperada por validação |
| F8 | Linhagem (OpenLineage) e catálogo | ⏳ | gate: grafo de linhagem do pipeline gerado e testado |
