"""Análise de grafo de transferências (NetworkX): features de nó e detecção de padrões.

A detecção roda em *micro-batches* (passo de 10 min, olhando 1 h para trás). Cada transação recebe
``graph_flag_ts`` = o primeiro passo em que o padrão ficou visível. Isso é um alerta **retrospectivo** (a
transação já pode ter sido liquidada); só usa dados até o instante do passo, sem olhar o futuro.
"""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd

STEP_S = 600
LOOKBACK_S = 3600
CASHOUT_RATIO = 0.7
HUB_MIN_SENDERS = 5
HUB_MAX_TTCO_S = 900
CHAIN_MIN_TX = 3
CHAIN_MAX_GAP_S = 600
CHAIN_MIN_KEEP = 0.8
_PRIORITY = {"cycle": 0, "chain": 1, "mule_hub": 2}


def build_graph(window: pd.DataFrame) -> nx.DiGraph:
    g = nx.DiGraph()
    for s, r, a in zip(window["sender"].tolist(), window["receiver"].tolist(), window["amount"].tolist()):
        if g.has_edge(s, r):
            g[s][r]["amount"] += float(a)
            g[s][r]["n"] += 1
        else:
            g.add_edge(s, r, amount=float(a), n=1)
    return g


def find_cycles(g: nx.DiGraph, min_len: int = 3, max_len: int = 4) -> list[tuple]:
    """Ciclos simples de 3..4 nós (ida e volta entre dois nós é comportamento normal e fica de fora)."""
    return [tuple(c) for c in nx.simple_cycles(g, length_bound=max_len) if len(c) >= min_len]


def time_to_cash_out(window: pd.DataFrame, node: str, ratio: float = CASHOUT_RATIO) -> float:
    """Segundos entre a última entrada e o instante em que as saídas acumuladas atingem ``ratio`` do total recebido."""
    inn = window[window["receiver"] == node].sort_values("ts")
    out = window[window["sender"] == node].sort_values("ts")
    if inn.empty or out.empty:
        return float("nan")
    cum = out["amount"].cumsum().to_numpy()
    ok = cum >= ratio * inn["amount"].sum()
    if not ok.any():
        return float("nan")
    tc = out["ts"].iloc[int(np.argmax(ok))]
    prior = inn[inn["ts"] < tc]
    if prior.empty:
        return float("nan")
    return float((tc - prior["ts"].max()).total_seconds())


def node_features(window: pd.DataFrame, full: bool = True) -> pd.DataFrame:
    """Features por conta numa janela. ``full=False`` pula pagerank/betweenness (usado na detecção)."""
    g = build_graph(window)
    nodes = list(g.nodes)
    cyc = find_cycles(g)
    cyc_count = {n: 0 for n in nodes}
    for c in cyc:
        for n in c:
            cyc_count[n] += 1
    comp = {}
    for c in nx.weakly_connected_components(g):
        for n in c:
            comp[n] = len(c)
    rows = []
    for n in nodes:
        i, o = g.in_degree(n), g.out_degree(n)
        rows.append(
            dict(
                account=n,
                in_degree=i,
                out_degree=o,
                unique_counterparties=len(set(g.predecessors(n)) | set(g.successors(n))),
                fan_in_ratio=i / (i + o) if i + o else 0.0,
                fan_out_ratio=o / (i + o) if i + o else 0.0,
                cycle_count=cyc_count[n],
                component_size=comp[n],
                time_to_cash_out_s=time_to_cash_out(window, n) if (i and o) else float("nan"),
            )
        )
    df = pd.DataFrame(rows)
    if full and len(g):
        pr = nx.pagerank(g, weight="amount")
        bt = nx.betweenness_centrality(g)
        df["pagerank"] = df["account"].map(pr)
        df["betweenness"] = df["account"].map(bt)
    return df


def _chain_ids(window: pd.DataFrame) -> set[str]:
    """Transações que fazem parte de uma cadeia de >= 3 encaminhamentos rápidos (camadas/triangulação)."""
    w = window if window["ts"].is_monotonic_increasing else window.sort_values(["ts", "tx_id"])
    secs =((w["ts"] - pd.Timestamp("1970-01-01")).dt.total_seconds()).tolist()
    senders, receivers, amounts, ids = w["sender"].tolist(), w["receiver"].tolist(), w["amount"].tolist(), w["tx_id"].tolist()
    n = len(ids)
    by_recv: dict[str, list[int]] = {}
    for j, r in enumerate(receivers):
        by_recv.setdefault(r, []).append(j)
    prev: list[list[int]] = [[] for _ in range(n)]
    nxt: list[list[int]] = [[] for _ in range(n)]
    for j in range(n):
        a = amounts[j]
        for i in by_recv.get(senders[j], ()):
            dt = secs[j] - secs[i]
            ai = amounts[i]
            if 0 < dt <= CHAIN_MAX_GAP_S and CHAIN_MIN_KEEP * ai <= a <= ai * 1.001:
                prev[j].append(i)
                nxt[i].append(j)
    end = [1] * n
    for j in range(n):
        end[j] = 1 + max((end[i] for i in prev[j]), default=0)
    start = [1] * n
    for j in reversed(range(n)):
        start[j] = 1 + max((start[k] for k in nxt[j]), default=0)
    return {ids[j] for j in range(n) if end[j] + start[j] - 1 >= CHAIN_MIN_TX}


def detect_patterns(window: pd.DataFrame) -> dict[str, str]:
    """tx_id -> padrão (``cycle`` > ``chain`` > ``mule_hub``) para as transações da janela."""
    found: dict[str, str] = {}

    def mark(ids, pat):
        for t in ids:
            if t not in found or _PRIORITY[pat] < _PRIORITY[found[t]]:
                found[t] = pat

    g = build_graph(window)
    edges = set()
    for c in find_cycles(g):
        for k in range(len(c)):
            edges.add((c[k], c[(k + 1) % len(c)]))
    if edges:
        keys = list(zip(window["sender"], window["receiver"]))
        mark([t for t, k in zip(window["tx_id"], keys) if k in edges], "cycle")

    mark(_chain_ids(window), "chain")

    for node in g.nodes:
        if g.in_degree(node) >= HUB_MIN_SENDERS and g.out_degree(node) >= 2:
            ttco = time_to_cash_out(window, node)
            if not np.isnan(ttco) and ttco <= HUB_MAX_TTCO_S:
                m = (window["receiver"] == node) | (window["sender"] == node)
                mark(window.loc[m, "tx_id"], "mule_hub")
    return found


def microbatch_flags(silver_df: pd.DataFrame, step_s: int = STEP_S, lookback_s: int = LOOKBACK_S) -> pd.DataFrame:
    """Colunas: tx_id, graph_flag_ts, graph_pattern (apenas transações sinalizadas)."""
    df = silver_df.sort_values(["ts", "tx_id"], kind="stable").reset_index(drop=True)
    if df.empty:
        return pd.DataFrame({"tx_id": [], "graph_flag_ts": pd.to_datetime([]), "graph_pattern": []})
    secs = (df["ts"] - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy()
    first = int(np.ceil(secs[0] / step_s) * step_s)
    last = int(np.ceil(secs[-1] / step_s) * step_s)
    flagged: dict[str, tuple[pd.Timestamp, str]] = {}
    for s in range(first, last + 1, step_s):
        lo = int(np.searchsorted(secs, s - lookback_s, side="right"))
        hi = int(np.searchsorted(secs, s, side="right"))
        new_lo = int(np.searchsorted(secs, s - step_s, side="right"))
        if hi - new_lo <= 0 or hi - lo < CHAIN_MIN_TX:
            continue  # nenhuma transação nova neste passo: nada novo pode aparecer
        pats = detect_patterns(df.iloc[lo:hi])
        stamp = pd.Timestamp(s, unit="s")
        for tx_id, pat in pats.items():
            if tx_id not in flagged:
                flagged[tx_id] = (stamp, pat)
    return pd.DataFrame(
        [(k, v[0], v[1]) for k, v in flagged.items()], columns=["tx_id", "graph_flag_ts", "graph_pattern"]
    )
