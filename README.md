# 🛡️ Pix-Fraud-Decisioning-Lab — decisão antifraude em transações Pix/TED sintéticas, de regras versionadas a grafo, ML e ciclo de contestação

### Python 3.10 · pandas · NetworkX · scikit-learn · PyYAML · SQLite · matplotlib · pytest · (PySpark/Delta: escrito, não executado)

[![ci](https://github.com/Yuri-Fernando/Pix-Fraud-Decisioning-Lab/actions/workflows/ci.yml/badge.svg)](https://github.com/Yuri-Fernando/Pix-Fraud-Decisioning-Lab/actions/workflows/ci.yml)
![testes](https://img.shields.io/badge/testes-88%20passando%20%C2%B7%201%20NOT__RUN-0a8a0a)
![PR-AUC](https://img.shields.io/badge/PR--AUC%20teste%20(sint%C3%A9tico)-0.975-2a78d6)
![dados](https://img.shields.io/badge/dados-100%25%20sint%C3%A9ticos-c8742a)
![versão](https://img.shields.io/badge/vers%C3%A3o-v0.1.0-4a5563) ![license](https://img.shields.io/badge/license-MIT-4a5563)

> **Simulação educacional baseada em documentação pública; sem integração com SPI/DICT e sem operação bancária real.**
> Nenhum dado real, nenhum cliente, nenhuma experiência de produção em motor antifraude comercial é alegada aqui.

---

## 🟡 Status — MVP técnico funcional (v0.1.0)

🟡 **MVP técnico funcional — núcleo validado em dados sintéticos: 88 testes passando, 1 NOT_RUN (paridade Spark), relatório reprodutível por seed.**
O pipeline pandas (Bronze → Silver → Gold), o motor de regras, o grafo, o classificador, o simulador de ciclo MED, o monitor por regra e o gerenciador de casos rodam de ponta a ponta. O backend PySpark/Delta **está escrito mas não foi executado** (PySpark não está instalado e o único Java do ambiente é o 1.8). Kafka/Redpanda e dashboards interativos não fazem parte desta versão.

| Área | Estado | Evidência |
|---|---|---|
| Gerador sintético com 8 padrões de fraude | ✅ implementado e testado | `tests/test_generator_medallion.py` |
| Bronze/Silver/Gold (pandas) com features *point-in-time* | ✅ implementado e testado (teste de vazamento por truncamento) | idem |
| Motor de regras YAML + fail-safe | ✅ implementado e testado (11 regras, positivo e negativo) | `tests/test_rules.py` |
| Grafo (NetworkX) e detecção em micro-batch | ✅ implementado e testado | `tests/test_graph.py` |
| ML + split temporal + controle de vazamento | ✅ implementado e testado | `tests/test_scoring_ml.py` |
| Simulador de estados Pix/MED | ✅ implementado; **prazos são placeholders** | `tests/test_med_monitor.py` |
| Monitor por regra + varredura de limiar | ✅ implementado e testado | `tests/test_med_monitor.py` |
| Casos (SQLite) + triagem LLM consultiva | ✅ implementado; provider Claude testado só com cliente simulado | `tests/test_cases_llm.py` |
| Backend PySpark + Delta | ⚠️ **escrito, NOT_RUN** | `src/pixfraud/medallion_spark.py` |
| Streaming Kafka/Redpanda, Neo4j, Unity Catalog | ⏳ não iniciado | [ROADMAP](ROADMAP.md) |

---

## Descrição / Contexto

Laboratório para estudar, de forma reprodutível, como uma **decisão antifraude transacional** é montada: regras versionadas com *reason codes* e evidência, sinais de grafo (contas mula, ciclos, triangulação), um classificador supervisionado como terceiro sinal, uma decisão final `APPROVE / REVIEW / BLOCK` com piso nas regras, o ciclo de vida de uma transação contestada (modelo didático inspirado no fluxo de MED) e o acompanhamento por regra (precisão, captura de valor, custo de falso positivo).

Tudo roda sobre transações **geradas por código** a partir de uma *seed*; o rótulo de fraude vem do injetor e é mantido numa tabela separada, de modo que nenhuma etapa a jusante consegue lê-lo por engano.

## 🧭 Origem do Projeto

O repositório nasceu de uma lacuna de portfólio: os projetos existentes cobrem *scoring* de crédito (RiskCredit), regras determinísticas com auditoria (ReconPilot) e controles com aprovação humana (SAP-FlowGuard), mas nenhum trata **fraude transacional**. Conclusões que definiram o desenho:

1. Fraude e crédito são problemas diferentes — por isso é um repositório novo, e não uma extensão do RiskCredit.
2. O motor de regras segue o padrão já usado no ReconPilot: determinístico, versionado, com *reason code* e evidência por decisão.
3. O LLM, se usado, é **consultivo** (resumo, hipóteses, checklist); nunca decide bloqueio. Isso é imposto por teste e por *trigger* no banco, não só por convenção.
4. Regras do Banco Central (prazos do MED etc.) **não foram inventadas**: viram constantes configuráveis marcadas como placeholder, a confirmar na documentação oficial antes de qualquer uso que dependa delas.
5. Spark só entra onde há ganho real; como o ambiente não o executa, o backend ficou como código documentado e **NOT_RUN**, sem resultado declarado.

## 🎯 Objetivo

- Gerar transações Pix/TED sintéticas reprodutíveis, com fraudes injetadas e rotuladas à parte.
- Calcular features sem olhar o futuro (verificado por teste).
- Decidir com regras versionadas, grafo e ML, sempre com motivo e evidência.
- Medir cada regra (hits, precisão, captura de valor, custo de falso positivo) e mostrar o *trade-off* de limiares.
- Simular o ciclo de vida de uma transação contestada com transições válidas e prazos configuráveis.
- Manter humano e motor separados: o analista resolve o caso; o LLM só escreve texto de apoio.

## 🔬 Linha de Pesquisa / Desenvolvimento

Detecção de fraude transacional · engenharia de features *point-in-time* · análise de grafos (mulas, ciclos, camadas) · avaliação temporal sem vazamento · governança de regras (calibração por limiar) · máquinas de estado · IA consultiva com limites impostos por construção.

## 🏗️ Arquitetura

```text
Transações sintéticas (seed)  ──►  Bronze  (como chegou + metadados)
                                      ↓
                                   Silver  (tipado, sem duplicata; inválidos → quarentena com motivo)
                                      ↓
                                   Gold    (features point-in-time + flags de grafo em micro-batch)
                                      ↓
        ┌──────────────────────┬──────────────────┬───────────────────────┐
     Regras YAML (11)       Grafo (NetworkX)    ML (HistGradientBoosting)
   reason codes+evidência   ciclo/cadeia/hub    split temporal + purga
        └──────────────────────┴──────────────────┴───────────────────────┘
                                      ↓  noisy-OR (piso = decisão das regras)
                          APPROVE / REVIEW / BLOCK  +  score
                                      ↓
              Casos (SQLite, campos de decisão imutáveis) ──► Analista humano
                                      ↓                          ▲
                     Triagem consultiva (template | Claude opcional)
                                      ↓
                Monitor por regra · varredura de limiar · simulador MED · relatório
```

| Módulo | Função | Teste |
|---|---|---|
| `generator.py` | transações, contas e rótulos separados; 8 padrões de fraude + tráfego legítimo "difícil" | `test_generator_medallion.py` |
| `medallion.py` | Bronze/Silver/Gold (pandas) | `test_generator_medallion.py` |
| `medallion_spark.py` | tradução para PySpark+Delta (**NOT_RUN**) | `test_pipeline_report_spark.py` |
| `rules/engine.py`, `rules/rules_v1.yaml` | motor determinístico, fail-safe, parâmetros por regra | `test_rules.py` |
| `graph.py` | features de nó, ciclos, cadeias, hubs de mula, micro-batch | `test_graph.py` |
| `ml.py`, `scoring.py` | classificador, split temporal, combinação de sinais | `test_scoring_ml.py` |
| `med.py` | máquina de estados do ciclo de contestação | `test_med_monitor.py` |
| `monitor.py` | desempenho por regra e varredura de limiar | `test_med_monitor.py` |
| `cases.py` | casos em SQLite e triagem consultiva | `test_cases_llm.py` |
| `report.py`, `cli.py`, `pipeline.py` | relatório MD/HTML/PNG, CLI, orquestração | `test_pipeline_report_spark.py` |

## ⚙️ Funcionamento

1. `generator.generate(cfg)` devolve `(transactions, accounts, labels)`; os rótulos nunca entram nas tabelas de transação.
2. `bronze` → `silver`: duplicatas, valor não positivo, partes ausentes e autotransferência vão para a quarentena com motivo.
3. `gold` percorre as transações em ordem de tempo mantendo apenas o passado de cada conta (janelas de 5 min, 15 min, 30 min e 1 h) e roda a detecção de grafo em passos de 10 min com janela de 1 h.
4. O motor de regras avalia o YAML; qualquer erro do próprio motor vira `REVIEW` com `ENGINE_ERROR` (nunca `APPROVE`).
5. O classificador treina no passado (60% iniciais) e é avaliado no futuro (últimos 30%); a faixa intermediária é descartada como purga.
6. `scoring.combine` junta regras, ML e grafo por *noisy-OR* com pesos configuráveis; a decisão final nunca é mais branda que a das regras e o ML sozinho não alcança `BLOCK`.
7. Decisões `REVIEW/BLOCK` abrem casos; a triagem escreve apenas em `summary`; o analista resolve.

```text
sintético → bronze → silver → gold → regras + grafo + ML → decisão → caso → analista
                                          └────────► monitor por regra / relatório
```

## 🧠 Verificação / Modelagem

| Camada | O que prova | Resultado |
|---|---|---|
| Features sem vazamento | truncar o histórico em *k* não altera as *k* primeiras linhas; alertas de grafo com `graph_flag_ts ≤ T` são idênticos quando os dados são cortados em T | testes passando |
| Split temporal | `max(ts treino) < min(ts teste)` e existe faixa de purga entre eles | teste passando |
| Controle de rótulo embaralhado | com rótulos de treino permutados, o PR-AUC de teste cai a menos da metade do real | teste passando |
| Regras | cada uma dispara no caso positivo e não dispara no negativo; avaliação vetorizada = linha a linha | 11 regras cobertas |
| Fail-safe | feature ausente / operador inválido ⇒ `REVIEW` + `ENGINE_ERROR` | testes passando |
| LLM consultivo | texto malicioso do "resumo" não altera decisão; `UPDATE` em campo de decisão é abortado pelo banco | testes passando |

O oráculo é o próprio injetor de fraudes: o rótulo é conhecido por construção, o que permite medir sem ambiguidade — e é exatamente por isso que os números abaixo **não** representam desempenho em dados reais.

## 🧪 Desenvolvimento Experimental

Fluxo: gerar → limpar → featurizar → decidir → medir → ajustar limiares → relatório.

**Achados reais (não plantados):**

| Achado | Causa real | Correção |
|---|---|---|
| Primeira versão dos dados era fácil demais: toda conta nova era fraude, quase zero falso positivo | o injetor só criava contas jovens para fraudadores | adicionei contas legítimas recém-abertas, pagamentos grandes legítimos e "vaquinhas" entre amigos (geram falso positivo em PIX003/MULE001 — visíveis no relatório) |
| Pipeline levava ~100 s | `groupby` do pandas em janelas minúsculas (≈2 000 passos) e OpenMP com muitos núcleos no `HistGradientBoosting` | grafo e cadeia reescritos com listas Python; treino limitado a 2 *threads* (`threadpoolctl`). Resultado idêntico, ~58 s ponta a ponta |
| Detecção de cadeia lenta por `sort_values` repetido | janela já está ordenada | só reordena se necessário |

## 🛠️ Tecnologias

**Linguagem:** Python 3.10 · **Dados:** pandas, NumPy, SQLite · **Grafo:** NetworkX · **ML:** scikit-learn (`HistGradientBoostingClassifier`) · **Regras:** PyYAML · **Visualização:** matplotlib · **Testes:** pytest · **LLM (opcional):** SDK `anthropic` · **Big data (NOT_RUN):** PySpark, Delta Lake.

## 📊 Resultados

Medidos em `python -m pixfraud run` (seed 42, 14 dias + 3 de aquecimento). Fonte: [`reports/metrics.json`](reports/metrics.json) e [`reports/report.md`](reports/report.md).

| Item | Valor |
|---|---|
| Transações / fraudes | 8 536 / 292 (3,42%) |
| Teste (futuro, com purga) | 2 561 transações / 130 fraudes (prevalência 5,08%) |

**PR-AUC no teste** (linha de base = prevalência 0,051):

| Sinal | PR-AUC |
|---|---|
| ML isolado | 0,937 |
| Regras (score) | 0,848 |
| Combinado | **0,975** |

**Decisão no teste** (sinalizado = `REVIEW` ou `BLOCK`):

| Cenário | Precisão | Recall | Captura de valor | Taxa de falso positivo | Precisão do `BLOCK` | Recall do `BLOCK` |
|---|---|---|---|---|---|---|
| Só regras | 0,850 | 0,869 | 0,966 | 0,82% | 1,000 | 0,262 |
| Combinado | 0,862 | 0,962 | 0,990 | 0,82% | 1,000 | 0,608 |

**Varredura de limiar** (`VELOCITY001`, transações do mesmo remetente em 5 min, todo o período): ≥3 ⇒ 105 hits, recall 0,360, captura de valor 0,140; ≥5 ⇒ 55 hits, 0,188, 0,050; ≥8 ⇒ 15 hits, 0,051, 0,010. Nesta base sintética não houve falso positivo para essa regra; em outras (PIX002: precisão 0,508; MULE001: 0,609) o custo aparece.

**Como ler:** precisão/recall são calculados por transação contra o rótulo do injetor; "captura de valor" é a fração do valor fraudulento total sinalizada; o custo de falso positivo usa **R$ 12 por revisão, valor ilustrativo e configurável**. O alerta de grafo é retrospectivo: atraso mediano de detecção de 659,5 s (passo de 10 min). **Limite importante:** as fraudes são injetadas por padrões que as próprias regras conhecem; PR-AUC alto aqui prova que o pipeline funciona, não que detectaria fraude real.

## 🖼️ Evidências

<p align="center">
  <a href="reports/figures/pr_curves.png"><img src="reports/figures/pr_curves.png" width="46%"></a>
  <a href="reports/figures/sweep_velocity.png"><img src="reports/figures/sweep_velocity.png" width="46%"></a>
</p>
<p align="center"><sub>Curvas precisão×recall no período de teste (esquerda) e captura × falso positivo por limiar de VELOCITY001 (direita) — dados sintéticos.</sub></p>

Relatório completo: [`reports/report.md`](reports/report.md) · [`reports/report.html`](reports/report.html).

## 🚀 Aplicações

- Estudo e demonstração de arquitetura de decisão antifraude (regras + grafo + ML) com rastreabilidade.
- Base didática para discutir calibração de regras, custo de falso positivo e vazamento temporal.
- Ponto de partida para experimentos com Spark/Delta e *streaming* quando houver ambiente.

## 🔭 Visão de Longo Prazo

```text
MVP local (pandas)
   ↓ paridade medida com Spark/Delta
Pipeline em lote e streaming (Redpanda → Spark Structured Streaming)
   ↓
Grafo persistido (Neo4j) e features de rede em tempo quase real
   ↓
Linhagem de dados (OpenLineage) e catálogo
```

## 🗺️ Roadmap

- **F0 — Dados sintéticos e medalhão** ✅ Concluída — gerador, Bronze/Silver/Gold, teste de vazamento.
- **F1 — Regras, grafo, ML e combinação** ✅ Concluída — 11 regras, micro-batch de grafo, split temporal.
- **F2 — MED, monitor e casos** ✅ Concluída — máquina de estados, varredura de limiar, SQLite imutável.
- **F3 — Spark/Delta executado e comparado ao pandas** ⏳ Planejada — código escrito, **NOT_RUN**.
- **F4 — Streaming (Redpanda) e grafo persistido** ⏳ Planejada.
- **F5 — Prazos do MED conferidos na documentação oficial** ⏳ Planejada — hoje placeholders.

Detalhe em [ROADMAP.md](ROADMAP.md).

## 🕓 Histórico e Mudanças

| Versão | Data | O que mudou |
|---|---|---|
| v0.1.0 | 2026-10-20 | primeira versão: pipeline, regras, grafo, ML, MED, monitor, casos, relatório, CI |

Ver [CHANGELOG.md](CHANGELOG.md) e [WORKLOG.md](WORKLOG.md).

## 🔮 Próximos Passos

- ✅ **Concluídos nesta versão:** núcleo local completo e testado, relatório reprodutível.
- 🤝 **Dependem de terceiros/ambiente:** executar o backend Spark (JDK 11/17 + PySpark 3.5); conferir os prazos e estados do MED na documentação oficial do Banco Central.
- 🔧 **O que eu faria numa v2:** validar paridade Spark×pandas por teste automatizado; tornar as fraudes menos "legíveis" pelas regras (padrões adversariais); calibrar pesos por validação e não por hipótese; adicionar *streaming*.

## ▶️ Como rodar localmente

Pré-requisitos: Python ≥ 3.10 com `numpy pandas networkx scikit-learn scipy PyYAML matplotlib pytest`. O `anthropic` só é necessário para a triagem opcional com Claude (`pip install .[llm]`).

```bash
# a partir da raiz do repositório
export PYTHONPATH=src                 # Windows (cmd): set PYTHONPATH=src
python -m pytest                      # 88 passando, 1 NOT_RUN (Spark)
python -m pixfraud run --out reports  # gera relatório e métricas (~1 min)
python -m pixfraud run --out reports --cases reports/cases.sqlite   # + casos e triagem determinística
python -m pixfraud sweep              # varredura de limiar de VELOCITY001
python -m pixfraud med-demo           # ciclos do simulador MED
```

| Ambiente | Estado |
|---|---|
| Windows 11 + Python 3.10 | testado nesta revisão |
| Linux / macOS | **não verificado** nesta revisão (CI definido em `.github/workflows/ci.yml`, ainda não executado) |
| Docker | não incluído |
| Spark/Delta | **NOT_RUN** |

A triagem com Claude (`--llm`) exige `ANTHROPIC_API_KEY` no ambiente e só envia o JSON do caso sintético; sem chave ou com falha de rede cai no resumo determinístico. Não foi executada contra a API real nesta revisão.

## 📁 Estrutura do repositório

```text
src/pixfraud/
  generator.py  medallion.py  medallion_spark.py  graph.py  ml.py  scoring.py
  med.py  monitor.py  cases.py  pipeline.py  report.py  cli.py
  rules/engine.py  rules/rules_v1.yaml
tests/            suíte pytest (88 testes + 1 NOT_RUN)
docs/adr/         decisões de arquitetura
reports/          relatório, métricas e figuras da execução de referência (seed 42)
.github/workflows/ci.yml
```

Não versionados: bancos `*.sqlite`, `data/`, saídas Delta e caches (ver `.gitignore`).

## 📚 Documentação

| Documento | Conteúdo |
|---|---|
| [docs/adr/0001-pandas-primeiro-spark-opcional.md](docs/adr/0001-pandas-primeiro-spark-opcional.md) | por que o núcleo é pandas e o Spark é opcional |
| [docs/adr/0002-regras-yaml-fail-safe.md](docs/adr/0002-regras-yaml-fail-safe.md) | regras versionadas e comportamento em erro |
| [docs/adr/0003-grafo-em-micro-batch.md](docs/adr/0003-grafo-em-micro-batch.md) | alerta retrospectivo sem olhar o futuro |
| [docs/adr/0004-llm-consultivo.md](docs/adr/0004-llm-consultivo.md) | limites do LLM impostos por construção |
| [docs/adr/0005-med-placeholders.md](docs/adr/0005-med-placeholders.md) | simulação do MED e prazos não afirmados |
| [reports/report.md](reports/report.md) | resultado da execução de referência |
| [CHANGELOG.md](CHANGELOG.md) · [ROADMAP.md](ROADMAP.md) · [WORKLOG.md](WORKLOG.md) | histórico e planejamento |

## ⚠️ Limitações

- **Dados 100% sintéticos**, com fraudes injetadas por padrões conhecidos pelas regras: as métricas são otimistas por construção.
- **Spark/Delta não executado** (PySpark ausente; Java 1.8 apenas). O módulo é código não validado.
- **MED:** transições são modelagem didática; prazos são placeholders. Sem integração com SPI/DICT.
- **Pesos e limiares** das regras são hipóteses de partida, não calibrados com dados reais; o custo de revisão (R$ 12) é ilustrativo.
- **Alertas de grafo são retrospectivos** (micro-batch de 10 min): não bloqueiam antes da liquidação.
- **Tamanho:** ~8,5 mil transações; não há medição de escala.
- **Não verificado nesta revisão:** Linux/macOS, CI no GitHub, provider Claude contra a API real.

## Status

🟡 **MVP técnico funcional (v0.1.0)** — núcleo local validado em dados sintéticos (88 testes passando, 1 NOT_RUN); backend Spark escrito mas não executado; sem dados nem integrações reais.

## Contexto / Observações

Peça de portfólio e estudo, **não afiliada a nenhuma instituição financeira** e sem conexão com sistemas do Banco Central. Não contém dados de clientes. As métricas são de simulação e não estimam desempenho em produção; o custo por revisão e os prazos do MED são parâmetros ilustrativos.

## 🔗 Projetos Relacionados

| Projeto | Relação |
|---|---|
| [ReconPilot](https://github.com/Yuri-Fernando/reconpilot-ai) | mesmo padrão de regras determinísticas com *reason code* e auditoria |
| [RiskCredit](https://github.com/Yuri-Fernando/RiskCredit) | *scoring*, limiares, *drift* e monitoramento — domínio de crédito, não de fraude |
| [SAP-FlowGuard](https://github.com/Yuri-Fernando/SAP-FlowGuard) | motor de exceções *fail-closed* com aprovação humana |
| [AegisLLM](https://github.com/Yuri-Fernando/AegisLLM) | guardrails e políticas para uso de LLM |
| [Engineering-CAD-AI](https://github.com/Yuri-Fernando/Engineering-CAD-AI) | mesma disciplina de plano tipado, aprovação humana e trilha de auditoria, aplicada a desenhos CAD |

## 🤖 Autor

**Yuri Fernando Dubbern**

Engenharia Elétrica · Ciência da Computação · Inteligência Artificial ·
Sistemas Embarcados · Projeto de Hardware · Pesquisa e Desenvolvimento

[LinkedIn](https://www.linkedin.com/in/yuridubbern) · [GitHub](https://github.com/Yuri-Fernando) · [Lattes](http://lattes.cnpq.br/7151392692642166) · [Linktree](https://linktr.ee/yuri.f.dubbern)

## Licença

MIT — ver [LICENSE](LICENSE).
