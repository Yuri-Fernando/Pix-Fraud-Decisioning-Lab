import pandas as pd
import pytest

from pixfraud.med import (
    TRANSITIONS, InvalidTransition, MedCase, MedConfig, State, lifecycle_for_decision,
)
from pixfraud.monitor import rule_performance, threshold_sweep
from pixfraud.rules import RuleSet

T0 = pd.Timestamp("2026-01-10 10:00")


def path(case):
    return [s.value for s, *_ in case.history]


def test_approved_transaction_lifecycle():
    assert path(lifecycle_for_decision("t", "APPROVE", T0)) == ["CREATED", "AUTHORIZED", "SETTLED", "CLOSED"]


def test_blocked_transaction_is_rejected_before_settlement():
    c = lifecycle_for_decision("t", "BLOCK", T0)
    assert path(c) == ["CREATED", "REJECTED", "CLOSED"] and c.is_terminal


def test_review_confirmed_goes_through_med_and_returns():
    c = lifecycle_for_decision("t", "REVIEW", T0, "CONFIRMED_FRAUD")
    assert path(c) == ["CREATED", "AUTHORIZED", "SETTLED", "FLAGGED", "CAUTIONARY_BLOCK", "MED_OPENED", "ANALYSIS", "RETURNED", "CLOSED"]


def test_review_false_positive_closes_without_med():
    c = lifecycle_for_decision("t", "REVIEW", T0, "FALSE_POSITIVE")
    assert path(c) == ["CREATED", "AUTHORIZED", "SETTLED", "FLAGGED", "CLOSED"]


def test_review_pending_stays_flagged():
    assert lifecycle_for_decision("t", "REVIEW", T0).state == State.FLAGGED


@pytest.mark.parametrize(
    "start,to",
    [(State.CREATED, State.SETTLED), (State.SETTLED, State.MED_OPENED), (State.FLAGGED, State.RETURNED),
     (State.CLOSED, State.CREATED), (State.MED_OPENED, State.RETURNED), (State.REJECTED, State.AUTHORIZED)],
)
def test_every_invalid_transition_raises(start, to):
    assert to not in TRANSITIONS[start]
    case = MedCase("t")
    case.history[-1] = (start, T0, "x", "")
    with pytest.raises(InvalidTransition):
        case.advance(to, T0 + pd.Timedelta(minutes=1))


def test_closed_is_terminal_and_time_cannot_go_backwards():
    c = lifecycle_for_decision("t", "APPROVE", T0)
    assert TRANSITIONS[State.CLOSED] == frozenset()
    with pytest.raises(InvalidTransition):
        c.advance(State.AUTHORIZED, T0)
    c2 = MedCase("t").start(T0)
    with pytest.raises(InvalidTransition):
        c2.advance(State.AUTHORIZED, T0 - pd.Timedelta(minutes=1))


def test_invalid_analyst_outcome_is_rejected():
    with pytest.raises(InvalidTransition):
        lifecycle_for_decision("t", "REVIEW", T0, "MAYBE")


def test_deadlines_are_placeholders_and_configurable():
    cfg = MedConfig()
    assert cfg.is_placeholder is True
    c = MedCase("t", MedConfig(cautionary_block_max_hours=2.0)).start(T0)
    c.advance(State.AUTHORIZED, T0 + pd.Timedelta(minutes=1)).advance(State.SETTLED, T0 + pd.Timedelta(minutes=2))
    c.advance(State.FLAGGED, T0 + pd.Timedelta(minutes=3)).advance(State.CAUTIONARY_BLOCK, T0 + pd.Timedelta(minutes=4))
    assert not c.overdue(T0 + pd.Timedelta(hours=1))
    assert c.overdue(T0 + pd.Timedelta(hours=3))


# ---------------- monitoramento por regra ----------------

def _gold_labels():
    gold = pd.DataFrame({
        "tx_id": ["a", "b", "c", "d"],
        "ts": pd.to_datetime(["2026-01-10 10:00"] * 4),
        "sender": ["s1", "s1", "s2", "s3"],
        "amount": [100.0, 200.0, 300.0, 400.0],
    })
    labels = pd.DataFrame({"tx_id": list("abcd"), "label_fraud": [1, 0, 1, 1]})
    hits = pd.DataFrame({"R1": [True, True, True, False], "R2": [False, False, False, False]})
    return gold, labels, hits


def test_rule_performance_metrics_are_computed_exactly():
    gold, labels, hits = _gold_labels()
    p = rule_performance(hits, gold, labels, review_cost_brl=10.0).set_index("rule_id")
    r1 = p.loc["R1"]
    assert (r1.hits, r1.confirmed_fraud, r1.false_positive) == (3, 2, 1)
    assert r1.alerts == 2  # (s1, dia) e (s2, dia)
    assert r1.precision == pytest.approx(2 / 3)
    assert r1.recall == pytest.approx(2 / 3)  # 3 fraudes no total
    assert r1.fraud_capture_rate == pytest.approx((100 + 300) / (100 + 300 + 400))
    assert r1.blocked_value == pytest.approx(600.0)
    assert r1.false_positive_cost == pytest.approx(10.0)
    r2 = p.loc["R2"]
    assert r2.hits == 0 and r2.recall == 0 and pd.isna(r2.precision)


def test_threshold_sweep_trades_capture_for_false_positives(pipe):
    sweep = threshold_sweep(RuleSet.load(), pipe["gold"], pipe["labels"], "VELOCITY001", "min_tx_5m", [3, 5, 8])
    assert sweep["value"].tolist() == [3, 5, 8]
    assert sweep["hits"].is_monotonic_decreasing
    assert sweep["false_positive"].is_monotonic_decreasing
    assert sweep["fraud_capture_rate"].is_monotonic_decreasing
    assert (sweep["confirmed_fraud"] + sweep["false_positive"] == sweep["hits"]).all()
