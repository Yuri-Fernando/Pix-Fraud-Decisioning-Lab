import numpy as np
import pandas as pd
import pytest

from pixfraud.ml import ML_FEATURES, design_matrix, temporal_split, train_eval
from pixfraud.scoring import ScoreConfig, combine, graph_score


def _rules_df(decision, score, n=1):
    return pd.DataFrame({"tx_id": [f"T{i}" for i in range(n)], "decision": [decision] * n, "rule_score": [score] * n})


def test_ml_alone_can_never_reach_block():
    cfg = ScoreConfig()
    out = combine(_rules_df("APPROVE", 0.0), pd.Series([1.0]), pd.Series([""]), cfg)
    assert out["final_score"].iat[0] == pytest.approx(cfg.w_ml)
    assert out["final_decision"].iat[0] == "REVIEW"  # escala para revisão, nunca bloqueio


def test_final_decision_is_never_milder_than_rules():
    for d in ("APPROVE", "REVIEW", "BLOCK"):
        out = combine(_rules_df(d, 0.0), pd.Series([0.0]), pd.Series([""]))
        rank = {"APPROVE": 0, "REVIEW": 1, "BLOCK": 2}
        assert rank[out["final_decision"].iat[0]] >= rank[d]


def test_rules_block_is_kept_even_if_ml_and_graph_are_silent():
    out = combine(_rules_df("BLOCK", 0.8), pd.Series([0.0]), pd.Series([""]))
    assert out["final_decision"].iat[0] == "BLOCK"


def test_graph_cycle_plus_rules_can_escalate_to_block():
    out = combine(_rules_df("REVIEW", 0.5), pd.Series([0.3]), pd.Series(["cycle"]))
    assert out["final_decision"].iat[0] == "BLOCK" and bool(out["escalated_by_score"].iat[0])


def test_graph_score_mapping():
    assert graph_score(pd.Series(["cycle", "chain", "mule_hub", ""])).tolist() == [1.0, 1.0, 0.6, 0.0]


def test_design_matrix_has_no_labels_ids_or_graph_flags():
    banned = {"label_fraud", "fraud_pattern", "tx_id", "graph_pattern", "graph_flag_ts", "sender", "receiver", "ts"}
    assert not banned & set(ML_FEATURES)


def test_temporal_split_trains_strictly_before_test(pipe):
    g = pipe["gold"]
    train, test = temporal_split(g)
    assert not (train & test).any()
    assert g.loc[train, "ts"].max() < g.loc[test, "ts"].min()
    purge = g[~train & ~test]
    assert len(purge) > 0 and g.loc[train, "ts"].max() < purge["ts"].min() <= purge["ts"].max() < g.loc[test, "ts"].min()


def test_model_learns_real_signal_but_not_from_shuffled_labels(pipe):
    """Controle de vazamento: com rótulos embaralhados no treino, o PR-AUC de teste cai para perto da prevalência."""
    g, labels = pipe["gold"], pipe["labels"]
    real = pipe["ml"]["pr_auc_test"]
    shuffled = labels.copy()
    shuffled["label_fraud"] = np.random.default_rng(0).permutation(shuffled["label_fraud"].to_numpy())
    fake = train_eval(g, shuffled)["pr_auc_test"]
    prev = pipe["ml"]["test_prevalence"]
    assert real > 0.5
    assert fake < 0.3 and fake < real / 2, (real, fake, prev)


def test_design_matrix_shape(pipe):
    x = design_matrix(pipe["gold"])
    assert list(x.columns) == ML_FEATURES and len(x) == len(pipe["gold"])
    assert not x.isna().any().any()
