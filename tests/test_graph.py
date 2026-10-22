import pytest

from conftest import txs
from pixfraud.graph import detect_patterns, node_features, time_to_cash_out

CYCLE = txs([("c1", 0, "A", "B", 1000), ("c2", 3, "B", "C", 990), ("c3", 6, "C", "A", 980)])
MUTUAL = txs([("m1", 0, "A", "B", 100), ("m2", 5, "B", "A", 500)])  # ida e volta é normal
HUB = txs(
    [(f"in{i}", i * 2, f"S{i}", "H", 100) for i in range(5)]
    + [("out1", 15, "H", "D1", 200), ("out2", 17, "H", "D2", 200)]
)
MERCHANT = txs([(f"p{i}", i * 3, f"S{i}", "M1", 50 + i) for i in range(6)])  # recebe muito, não encaminha
CHAIN = txs([("h1", 0, "V", "D1", 1000), ("h2", 3, "D1", "D2", 940), ("h3", 6, "D2", "D3", 880)])
TWO_HOPS = txs([("h1", 0, "V", "D1", 1000), ("h2", 3, "D1", "D2", 940)])


def test_cycle_of_three_is_flagged_as_cycle():
    assert detect_patterns(CYCLE) == {"c1": "cycle", "c2": "cycle", "c3": "cycle"}


def test_two_node_back_and_forth_is_not_a_cycle():
    assert detect_patterns(MUTUAL) == {}


def test_mule_hub_flags_inbound_and_outbound_edges():
    pats = detect_patterns(HUB)
    assert set(pats) == {f"in{i}" for i in range(5)} | {"out1", "out2"}
    assert set(pats.values()) == {"mule_hub"}


def test_merchant_receiving_many_without_cash_out_is_not_flagged():
    assert detect_patterns(MERCHANT) == {}


def test_chain_needs_three_forwardings():
    assert set(detect_patterns(CHAIN)) == {"h1", "h2", "h3"}
    assert detect_patterns(TWO_HOPS) == {}


def test_forwarding_slower_than_gap_or_with_lower_share_is_not_a_chain():
    slow = txs([("h1", 0, "V", "D1", 1000), ("h2", 30, "D1", "D2", 940), ("h3", 33, "D2", "D3", 880)])
    partial = txs([("h1", 0, "V", "D1", 1000), ("h2", 3, "D1", "D2", 300), ("h3", 6, "D2", "D3", 280)])
    assert detect_patterns(slow) == {}
    assert detect_patterns(partial) == {}


def test_time_to_cash_out_measured_from_last_inbound():
    # entradas em 0,2,4,6,8 min (total 500); saídas 200 (min 15) e 200 (min 17): 70% de 500 = 350 só aos 17 min
    assert time_to_cash_out(HUB, "H") == pytest.approx(9 * 60)
    assert str(time_to_cash_out(HUB, "S0")) == "nan"


def test_node_features_columns_and_values():
    nf = node_features(HUB).set_index("account")
    h = nf.loc["H"]
    assert h["in_degree"] == 5 and h["out_degree"] == 2
    assert h["unique_counterparties"] == 7
    assert h["fan_in_ratio"] == pytest.approx(5 / 7) and h["fan_out_ratio"] == pytest.approx(2 / 7)
    assert h["component_size"] == 8
    assert {"pagerank", "betweenness", "cycle_count", "time_to_cash_out_s"} <= set(nf.columns)
    assert nf["pagerank"].sum() == pytest.approx(1.0, abs=1e-6)
    assert "pagerank" not in node_features(HUB, full=False).columns


def test_cycle_count_per_node():
    nf = node_features(CYCLE).set_index("account")
    assert (nf["cycle_count"] == 1).all()


def test_injected_graph_patterns_are_detected_in_generated_data(pipe):
    g, labels = pipe["gold"], pipe["labels"]
    m = g.merge(labels, on="tx_id")
    for pat in ("cycle", "chain", "mule"):
        sub = m[m.fraud_pattern == pat]
        assert len(sub) > 0
        assert (sub["graph_pattern"] != "").mean() >= 0.9, pat
    legit = m[m.label_fraud == 0]
    assert (legit["graph_pattern"] != "").mean() < 0.01  # vaquinha/lojistas legítimos quase nunca caem no grafo
