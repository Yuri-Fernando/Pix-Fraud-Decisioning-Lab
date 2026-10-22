import pandas as pd
import pytest

from conftest import SMALL
from pixfraud.generator import PATTERNS, generate, make_dirty
from pixfraud.medallion import GOLD_FEATURES, bronze, gold, silver


def test_generation_is_deterministic_for_same_seed():
    a = generate(SMALL)
    b = generate(SMALL)
    for x, y in zip(a, b):
        pd.testing.assert_frame_equal(x, y)


def test_different_seed_changes_data():
    from dataclasses import replace

    a, _, _ = generate(SMALL)
    b, _, _ = generate(replace(SMALL, seed=2))
    assert not a.equals(b)


def test_transactions_table_has_no_label_columns(pipe):
    tx, _, labels = generate(SMALL)
    assert not {"label_fraud", "fraud_pattern"} & set(tx.columns)
    assert set(labels.columns) == {"tx_id", "label_fraud", "fraud_pattern"}


def test_every_fraud_pattern_is_injected_after_warmup():
    tx, _, labels = generate(SMALL)
    lab = tx.merge(labels, on="tx_id")
    assert set(lab.loc[lab.label_fraud == 1, "fraud_pattern"]) == set(PATTERNS)
    warm_end = pd.Timestamp(SMALL.start) + pd.Timedelta(days=SMALL.warmup_days)
    assert lab.loc[lab.label_fraud == 1, "ts"].min() >= warm_end
    assert 0.005 < lab.label_fraud.mean() < 0.2


def test_silver_quarantines_duplicates_and_invalid_rows():
    tx, acc, _ = generate(SMALL)
    dirty = make_dirty(tx, n_duplicates=3, n_invalid=3)
    clean, quarantine = silver(bronze(dirty))
    assert len(clean) == len(tx)  # nada de legítimo foi perdido
    assert clean["tx_id"].is_unique
    assert set(quarantine["reason"]) == {"DUPLICATE_TX_ID", "INVALID_AMOUNT", "MISSING_PARTY", "SELF_TRANSFER"}
    assert len(quarantine) == 6
    assert (clean["amount"] > 0).all()


def test_gold_never_reads_label_columns():
    tx, acc, labels = generate(SMALL)
    s, _ = silver(bronze(tx))
    g = gold(s, acc, with_graph=False)
    assert not any("label" in c or "fraud_pattern" in c for c in g.columns)
    assert set(GOLD_FEATURES) <= set(g.columns)


def test_gold_features_are_point_in_time_no_future_leakage():
    """Truncar o histórico no instante k não pode alterar as features das k primeiras linhas."""
    tx, acc, _ = generate(SMALL)
    s, _ = silver(bronze(tx))
    full = gold(s, acc, with_graph=False)
    k = 1200
    head = gold(s.iloc[:k], acc, with_graph=False)
    cols = ["tx_id"] + GOLD_FEATURES
    pd.testing.assert_frame_equal(full[cols].iloc[:k].reset_index(drop=True), head[cols].reset_index(drop=True))


def test_graph_alerts_only_use_data_up_to_their_flag_time():
    """Alertas de grafo com graph_flag_ts <= T são idênticos quando os dados são cortados em T."""
    tx, acc, _ = generate(SMALL)
    s, _ = silver(bronze(tx))
    full = gold(s, acc)
    k = len(s) * 2 // 3
    cut = s.iloc[:k]
    part = gold(cut, acc)
    last_step = (cut["ts"].max() - pd.Timestamp("1970-01-01")).total_seconds() // 600 * 600
    horizon = pd.Timestamp(last_step, unit="s")
    a = full[full.graph_flag_ts <= horizon][["tx_id", "graph_flag_ts", "graph_pattern"]]
    b = part[part.graph_flag_ts <= horizon][["tx_id", "graph_flag_ts", "graph_pattern"]]
    assert len(a) > 0
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))


def test_unknown_receiver_account_is_treated_as_new_and_conservative():
    tx, acc, _ = generate(SMALL)
    s, _ = silver(bronze(tx))
    g = gold(s, acc.iloc[:5], with_graph=False)  # quase nenhuma conta conhecida
    unknown = ~g["receiver"].isin(acc.iloc[:5]["account_id"])
    assert (g.loc[unknown, "receiver_age_days"] == 0).all()
    assert (g.loc[unknown, "receiver_prior_med_count"] == 0).all()
