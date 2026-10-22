import pandas as pd
import pytest
import yaml

from conftest import row
from pixfraud.rules import RuleEngineError, RuleSet, safe_decide
from pixfraud.rules.engine import DEFAULT_RULES

RS = RuleSet.load()

# regra -> (overrides que disparam, overrides que NÃO disparam)
CASES = {
    "PIX001": (dict(is_new_beneficiary=True, amount=6000), dict(is_new_beneficiary=True, amount=4999)),
    "PIX002": (dict(amount_ratio=12, amount=1500), dict(amount_ratio=12, amount=900)),
    "PIX003": (dict(receiver_age_days=3, amount=2500), dict(receiver_age_days=3, amount=1999)),
    "VELOCITY001": (dict(sender_tx_count_5m=5), dict(sender_tx_count_5m=4)),
    "DEVICE001": (dict(new_device=True, amount_ratio=4, amount=1200), dict(new_device=False, amount_ratio=4, amount=1200)),
    "MULE001": (dict(receiver_fan_in_30m=5), dict(receiver_fan_in_30m=4)),
    "MULE002": (
        dict(sender_inflow_senders_30m=6, sender_outflow_ratio_15m=0.9),
        dict(sender_inflow_senders_30m=6, sender_outflow_ratio_15m=0.3),
    ),
    "FANOUT001": (dict(sender_fan_out_15m=5, is_new_beneficiary=True), dict(sender_fan_out_15m=5, is_new_beneficiary=False)),
    "GRAPH001": (dict(graph_pattern="cycle"), dict(graph_pattern="mule_hub")),
    "GRAPH002": (dict(graph_pattern="mule_hub"), dict(graph_pattern="cycle")),
    "MED001": (dict(receiver_prior_med_count=2, amount=600), dict(receiver_prior_med_count=1, amount=600)),
}


def test_every_rule_in_yaml_has_a_positive_and_negative_case():
    assert set(CASES) == {r.id for r in RS.rules}
    assert RS.version == "1.0.0"


def test_baseline_row_is_approved():
    out = RS.evaluate(row()).decisions
    assert out["decision"].iat[0] == "APPROVE"
    assert out["reason_codes"].iat[0] == []


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_rule_fires_on_positive_and_not_on_negative(rule_id):
    pos, neg = CASES[rule_id]
    rule = RS.get(rule_id)
    r_pos = RS.evaluate(row(**pos))
    r_neg = RS.evaluate(row(**neg))
    assert bool(r_pos.hits[rule_id].iat[0]) is True
    assert bool(r_neg.hits[rule_id].iat[0]) is False
    d = r_pos.decisions.iloc[0]
    assert rule.reason_code in d["reason_codes"]
    assert rule_id in d["rules_hit"]
    assert d["evidence"], "regra que dispara precisa deixar evidência"
    assert d["decision"] == rule.action or d["decision"] == "BLOCK"
    assert d["rule_score"] >= rule.weight - 1e-9


def test_block_rule_dominates_review_and_scores_combine_as_noisy_or():
    r = RS.evaluate(row(sender_inflow_senders_30m=6, sender_outflow_ratio_15m=0.9, receiver_fan_in_30m=6))
    d = r.decisions.iloc[0]
    assert d["decision"] == "BLOCK"
    assert set(d["rules_hit"]) == {"MULE001", "MULE002"}
    assert d["rule_score"] == pytest.approx(1 - (1 - 0.50) * (1 - 0.80))


def test_missing_feature_is_fail_safe_review_not_approve():
    df = row().drop(columns=["amount_ratio"])
    with pytest.raises(RuleEngineError):
        RS.evaluate(df)
    out = safe_decide(RS, df).decisions
    assert out["decision"].iat[0] == "REVIEW"
    assert out["reason_codes"].iat[0] == ["ENGINE_ERROR"]


def test_unknown_operator_is_fail_safe():
    bad = RuleSet.from_dict(
        {"version": "x", "rules": [dict(id="R1", name="n", action="BLOCK", weight=0.5, reason_code="X",
                                         when={"all": [{"feature": "amount", "op": "~=", "value": 1}]})]}
    )
    out = safe_decide(bad, row()).decisions
    assert out["decision"].iat[0] == "REVIEW" and out["reason_codes"].iat[0] == ["ENGINE_ERROR"]


def test_nan_feature_value_does_not_fire_and_does_not_crash():
    out = RS.evaluate(row(amount_ratio=float("nan"))).decisions
    assert out["decision"].iat[0] == "APPROVE"


@pytest.mark.parametrize(
    "mutate,msg",
    [
        (lambda r: r["rules"][0].update(action="APPROVE"), "ação inválida"),
        (lambda r: r["rules"][0].update(weight=1.5), "peso fora"),
        (lambda r: r["rules"].append(dict(r["rules"][0])), "duplicados"),
        (lambda r: r["rules"][0].pop("reason_code"), "sem campo"),
        (lambda r: r.pop("version"), "version"),
    ],
)
def test_invalid_rule_definitions_are_rejected(mutate, msg):
    raw = yaml.safe_load(DEFAULT_RULES.read_text(encoding="utf-8"))
    mutate(raw)
    with pytest.raises(RuleEngineError, match=msg):
        RuleSet.from_dict(raw)


def test_with_params_overrides_threshold_without_touching_original():
    strict = RS.with_params({"VELOCITY001": {"min_tx_5m": 8}})
    assert strict.get("VELOCITY001").params["min_tx_5m"] == 8
    assert RS.get("VELOCITY001").params["min_tx_5m"] == 5
    df = row(sender_tx_count_5m=6)
    assert RS.evaluate(df).hits["VELOCITY001"].iat[0]
    assert not strict.evaluate(df).hits["VELOCITY001"].iat[0]
    with pytest.raises(RuleEngineError):
        RS.with_params({"VELOCITY001": {"nao_existe": 1}})
    with pytest.raises(RuleEngineError):
        RS.with_params({"NOPE": {"x": 1}})


def test_vectorised_evaluation_matches_row_by_row():
    df = pd.concat(
        [row(tx_id=f"T{i}", **(CASES[k][i % 2])) for i, k in enumerate(sorted(CASES))], ignore_index=True
    )
    whole = RS.evaluate(df).decisions["decision"].tolist()
    each = [RS.evaluate(df.iloc[[i]]).decisions["decision"].iat[0] for i in range(len(df))]
    assert whole == each
