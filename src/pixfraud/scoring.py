"""Combinação de sinais (regras + ML + grafo) e decisão final.

Regras de projeto:
* o ML sozinho nunca alcança o limiar de BLOCK (w_ml < block_threshold);
* a decisão final nunca é *menos* severa do que a decisão das regras;
* LLM não participa da decisão (ver :mod:`pixfraud.cases`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from pixfraud.rules.engine import ACTION_RANK

_RANK_ACTION = {v: k for k, v in ACTION_RANK.items()}
GRAPH_STRENGTH = {"cycle": 1.0, "chain": 1.0, "mule_hub": 0.6}


@dataclass(frozen=True)
class ScoreConfig:
    w_rules: float = 1.0
    w_ml: float = 0.6
    w_graph: float = 0.8
    review_threshold: float = 0.35
    block_threshold: float = 0.80


def graph_score(patterns: pd.Series) -> pd.Series:
    return patterns.map(GRAPH_STRENGTH).fillna(0.0).astype(float)


def combine(
    rules_decisions: pd.DataFrame,
    ml_proba: pd.Series | None,
    graph_patterns: pd.Series | None,
    cfg: ScoreConfig = ScoreConfig(),
) -> pd.DataFrame:
    """Noisy-OR: ``1 - Π(1 - w_i * s_i)``. Todos os insumos precisam ter o mesmo índice."""
    idx = rules_decisions.index
    r = rules_decisions["rule_score"].astype(float)
    m = ml_proba.reindex(idx).fillna(0.0) if ml_proba is not None else pd.Series(0.0, index=idx)
    g = graph_score(graph_patterns.reindex(idx)) if graph_patterns is not None else pd.Series(0.0, index=idx)
    score = 1 - (1 - cfg.w_rules * r) * (1 - cfg.w_ml * m) * (1 - cfg.w_graph * g)
    thr_rank = np.where(score >= cfg.block_threshold, 2, np.where(score >= cfg.review_threshold, 1, 0))
    rules_rank = rules_decisions["decision"].map(ACTION_RANK).to_numpy()
    final = np.maximum(thr_rank, rules_rank)
    return pd.DataFrame(
        {
            "tx_id": rules_decisions["tx_id"],
            "final_score": score,
            "final_decision": [_RANK_ACTION[x] for x in final],
            "escalated_by_score": thr_rank > rules_rank,
        },
        index=idx,
    )
