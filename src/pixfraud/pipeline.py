"""Orquestra: gerar → bronze/silver/gold → regras → ML → combinação → métricas."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from pixfraud.generator import GenConfig, generate
from pixfraud.medallion import bronze, gold, silver
from pixfraud.ml import train_eval
from pixfraud.monitor import rule_performance, threshold_sweep
from pixfraud.rules.engine import RuleSet, safe_decide
from pixfraud.scoring import ScoreConfig, combine


def evaluate_decisions(decision: pd.Series, y: pd.Series, amount: pd.Series) -> dict:
    """Métricas de decisão: 'sinalizado' = REVIEW ou BLOCK."""
    flagged = (decision != "APPROVE").to_numpy()
    block = (decision == "BLOCK").to_numpy()
    yy = y.to_numpy().astype(bool)
    amt = amount.to_numpy()
    tp, fp = int((flagged & yy).sum()), int((flagged & ~yy).sum())
    btp, bfp = int((block & yy).sum()), int((block & ~yy).sum())
    n_fraud = int(yy.sum())
    fraud_value = float(amt[yy].sum())
    return {
        "n": int(len(y)),
        "n_fraud": n_fraud,
        "flagged": int(flagged.sum()),
        "tp": tp,
        "fp": fp,
        "precision": tp / (tp + fp) if tp + fp else float("nan"),
        "recall": tp / n_fraud if n_fraud else float("nan"),
        "block_precision": btp / (btp + bfp) if btp + bfp else float("nan"),
        "block_recall": btp / n_fraud if n_fraud else float("nan"),
        "fraud_value_captured_rate": float(amt[flagged & yy].sum()) / fraud_value if fraud_value else float("nan"),
        "flagged_value": float(amt[flagged].sum()),
        "false_positive_rate": fp / int((~yy).sum()) if (~yy).sum() else float("nan"),
    }


def _pr(y: pd.Series, score: pd.Series) -> float:
    return float(average_precision_score(y, score)) if y.sum() > 0 else float("nan")


def run_pipeline(
    cfg: GenConfig = GenConfig(),
    score_cfg: ScoreConfig = ScoreConfig(),
    with_graph: bool = True,
    ruleset: RuleSet | None = None,
) -> dict:
    tx, accounts, labels = generate(cfg)
    b = bronze(tx)
    s, quarantine = silver(b)
    g = gold(s, accounts, with_graph=with_graph)
    rs = ruleset or RuleSet.load()
    res = safe_decide(rs, g)
    ml = train_eval(g, labels, seed=cfg.seed)
    comb = combine(res.decisions, ml["proba"], g["graph_pattern"], score_cfg)

    y = ml["y"]
    test = ml["test_mask"]
    pattern = g[["tx_id"]].merge(labels, on="tx_id", how="left")["fraud_pattern"].fillna("")
    amount = g["amount"]

    rules_all = evaluate_decisions(res.decisions["decision"], y, amount)
    rules_test = evaluate_decisions(res.decisions.loc[test, "decision"], y[test], amount[test])
    comb_test = evaluate_decisions(comb.loc[test, "final_decision"], y[test], amount[test])

    graph_y = y[g["graph_pattern"] != ""]
    pr_auc = {
        "ml_only": ml["pr_auc_test"],
        "rules_only": _pr(y[test], res.decisions.loc[test, "rule_score"]),
        "combined": _pr(y[test], comb.loc[test, "final_score"]),
        "prevalence_test": ml["test_prevalence"],
    }

    by_pattern = []
    for pat in sorted(p for p in pattern.unique() if p):
        m = (pattern == pat).to_numpy()
        mt = m & test.to_numpy()
        by_pattern.append(
            dict(
                pattern=pat,
                n_tx=int(m.sum()),
                rules_recall_all=float((res.decisions["decision"][m] != "APPROVE").mean()),
                n_tx_test=int(mt.sum()),
                combined_recall_test=float((comb["final_decision"][mt] != "APPROVE").mean()) if mt.any() else float("nan"),
            )
        )
    perf = rule_performance(res.hits, g, labels) if len(res.hits.columns) else pd.DataFrame()
    sweep = threshold_sweep(rs, g, labels, "VELOCITY001", "min_tx_5m", [3, 5, 8]) if with_graph or True else pd.DataFrame()

    delay = (g["graph_flag_ts"] - g["ts"]).dt.total_seconds().dropna()
    metrics = {
        "config": {k: v for k, v in cfg.__dict__.items()},
        "rules_version": rs.version,
        "dataset": {
            "n_transactions": int(len(g)),
            "n_fraud": int(y.sum()),
            "fraud_rate": float(y.mean()),
            "n_quarantine": int(len(quarantine)),
            "n_train": ml["n_train"],
            "n_test": ml["n_test"],
            "n_fraud_test": int(y[test].sum()),
        },
        "pr_auc_test": pr_auc,
        "rules_only_all": rules_all,
        "rules_only_test": rules_test,
        "combined_test": comb_test,
        "graph": {
            "n_flagged": int((g["graph_pattern"] != "").sum()),
            "precision": float(graph_y.mean()) if len(graph_y) else float("nan"),
            "median_detection_delay_s": float(delay.median()) if len(delay) else float("nan"),
        },
        "by_pattern": by_pattern,
    }
    return {
        "metrics": metrics,
        "gold": g,
        "labels": labels,
        "accounts": accounts,
        "quarantine": quarantine,
        "rule_result": res,
        "ml": ml,
        "combined": comb,
        "rule_performance": perf,
        "sweep": sweep,
        "ruleset": rs,
    }
