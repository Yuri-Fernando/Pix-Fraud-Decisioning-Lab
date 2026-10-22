"""Monitoramento de desempenho por regra e varredura de limiar."""

from __future__ import annotations

import pandas as pd

from pixfraud.rules.engine import RuleSet, safe_decide

REVIEW_COST_BRL = 12.0  # custo ILUSTRATIVO de uma revisão manual; configurável, não é dado real


def rule_performance(
    hits: pd.DataFrame,
    gold: pd.DataFrame,
    labels: pd.DataFrame,
    review_cost_brl: float = REVIEW_COST_BRL,
) -> pd.DataFrame:
    """Uma linha por regra: hits, alerts, confirmed_fraud, false_positive, precision, recall, fraud_capture_rate,
    blocked_value, false_positive_cost.

    * ``alerts``: pares (remetente, dia) distintos com ao menos um hit — o que um analista veria agrupado.
    * ``fraud_capture_rate``: valor fraudulento capturado / valor fraudulento total (ponderado por valor).
    * ``false_positive_cost``: falsos positivos × custo de revisão (ilustrativo).
    """
    y = gold[["tx_id"]].merge(labels[["tx_id", "label_fraud"]], on="tx_id", how="left")["label_fraud"].fillna(0).astype(int).to_numpy()
    amount = gold["amount"].to_numpy()
    total_fraud = int(y.sum())
    total_fraud_value = float(amount[y == 1].sum())
    day = gold["ts"].dt.date.to_numpy()
    sender = gold["sender"].to_numpy()
    rows = []
    for rid in hits.columns:
        m = hits[rid].to_numpy().astype(bool)
        n = int(m.sum())
        conf = int((m & (y == 1)).sum())
        fp = int((m & (y == 0)).sum())
        rows.append(
            dict(
                rule_id=rid,
                hits=n,
                alerts=len(set(zip(sender[m], day[m]))),
                confirmed_fraud=conf,
                false_positive=fp,
                precision=conf / n if n else float("nan"),
                recall=conf / total_fraud if total_fraud else float("nan"),
                fraud_capture_rate=float(amount[m & (y == 1)].sum()) / total_fraud_value if total_fraud_value else float("nan"),
                blocked_value=float(amount[m].sum()),
                false_positive_cost=fp * review_cost_brl,
            )
        )
    return pd.DataFrame(rows)


def threshold_sweep(
    ruleset: RuleSet,
    gold: pd.DataFrame,
    labels: pd.DataFrame,
    rule_id: str,
    param: str,
    values: list,
    review_cost_brl: float = REVIEW_COST_BRL,
) -> pd.DataFrame:
    """Reavalia uma regra para vários valores de um parâmetro (ex.: VELOCITY001.min_tx_5m = 3/5/8)."""
    rows = []
    for v in values:
        res = safe_decide(ruleset.with_params({rule_id: {param: v}}), gold)
        perf = rule_performance(res.hits[[rule_id]], gold, labels, review_cost_brl).iloc[0].to_dict()
        perf["param"] = param
        perf["value"] = v
        rows.append(perf)
    cols = ["param", "value", "hits", "confirmed_fraud", "false_positive", "precision", "recall",
            "fraud_capture_rate", "false_positive_cost"]
    return pd.DataFrame(rows)[cols]
