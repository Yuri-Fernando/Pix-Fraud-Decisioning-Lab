"""Camadas Bronze → Silver → Gold (backend pandas).

* Bronze: dado como chegou (+ metadados de ingestão).
* Silver: tipado, sem duplicatas, linhas inválidas isoladas em quarentena com motivo.
* Gold: features *point-in-time* por transação — cada linha só enxerga o passado (e a si mesma).

O backend PySpark equivalente está em :mod:`pixfraud.medallion_spark` (escrito, não executado aqui).
"""

from __future__ import annotations

from collections import defaultdict, deque

import numpy as np
import pandas as pd

from pixfraud.graph import microbatch_flags

GOLD_FEATURES = [
    "hour",
    "amount_ratio",
    "is_new_beneficiary",
    "new_device",
    "sender_tx_count_5m",
    "sender_tx_count_1h",
    "sender_fan_out_15m",
    "receiver_fan_in_30m",
    "sender_inflow_senders_30m",
    "sender_inflow_amount_30m",
    "sender_outflow_ratio_15m",
    "receiver_age_days",
    "receiver_prior_med_count",
]


def bronze(tx: pd.DataFrame, source: str = "synthetic") -> pd.DataFrame:
    out = tx.copy()
    out["ingested_at"] = pd.to_datetime(out["ts"]) + pd.Timedelta(seconds=2)
    out["source"] = source
    return out


def silver(bronze_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devolve (limpo, quarentena). A quarentena preserva a linha original e o motivo."""
    df = bronze_df.copy()
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    dup = df.duplicated("tx_id", keep="first")
    conds = [
        dup,
        df["ts"].isna(),
        ~(df["amount"] > 0),
        df["sender"].isna() | df["receiver"].isna(),
        df["sender"] == df["receiver"],
    ]
    reasons = ["DUPLICATE_TX_ID", "INVALID_TIMESTAMP", "INVALID_AMOUNT", "MISSING_PARTY", "SELF_TRANSFER"]
    reason = np.select(conds, reasons, default="")
    bad = reason != ""
    quarantine = df[bad].assign(reason=reason[bad])
    clean = df[~bad].sort_values(["ts", "tx_id"], kind="stable").reset_index(drop=True)
    clean["device_id"] = clean["device_id"].fillna("UNKNOWN")
    return clean, quarantine.reset_index(drop=True)


def _features(df: pd.DataFrame, accounts: pd.DataFrame) -> pd.DataFrame:
    secs = (df["ts"] - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy()
    send_hist: dict = defaultdict(deque)  # sender -> (t, receiver, amount), janela 1 h
    recv_hist: dict = defaultdict(deque)  # receiver -> (t, sender, amount), janela 30 min
    seen_recv: dict = defaultdict(set)
    seen_dev: dict = defaultdict(set)
    amts: dict = defaultdict(list)
    cols: dict[str, list] = {k: [] for k in GOLD_FEATURES if k not in ("hour", "receiver_age_days", "receiver_prior_med_count")}

    for t, s, r, a, dev in zip(secs, df["sender"], df["receiver"], df["amount"], df["device_id"]):
        sh = send_hist[s]
        while sh and t - sh[0][0] > 3600:
            sh.popleft()
        rh = recv_hist[r]
        while rh and t - rh[0][0] > 1800:
            rh.popleft()
        ih = recv_hist[s]
        while ih and t - ih[0][0] > 1800:
            ih.popleft()

        cols["sender_tx_count_5m"].append(1 + sum(1 for x in sh if t - x[0] <= 300))
        cols["sender_tx_count_1h"].append(1 + len(sh))
        cols["sender_fan_out_15m"].append(len({x[1] for x in sh if t - x[0] <= 900} | {r}))
        cols["receiver_fan_in_30m"].append(len({x[1] for x in rh} | {s}))
        in_amt = float(sum(x[2] for x in ih))
        cols["sender_inflow_senders_30m"].append(len({x[1] for x in ih}))
        cols["sender_inflow_amount_30m"].append(in_amt)
        out15 = a + sum(x[2] for x in sh if t - x[0] <= 900)
        cols["sender_outflow_ratio_15m"].append(float(out15 / in_amt) if in_amt > 0 else 0.0)
        cols["is_new_beneficiary"].append(r not in seen_recv[s])
        cols["new_device"].append(bool(seen_dev[s]) and dev not in seen_dev[s])
        hist = amts[s]
        med = float(np.median(hist[-50:])) if len(hist) >= 3 else 0.0
        cols["amount_ratio"].append(float(a / med) if med > 0 else 1.0)

        sh.append((t, r, a))
        recv_hist[r].append((t, s, a))
        seen_recv[s].add(r)
        seen_dev[s].add(dev)
        hist.append(a)

    out = pd.DataFrame(cols, index=df.index)
    acc = accounts.set_index("account_id")
    out["hour"] = df["ts"].dt.hour.astype(int)
    # conta desconhecida é tratada como nova e sem histórico (conservador)
    out["receiver_age_days"] = df["receiver"].map(acc["age_days"]).fillna(0).astype(int)
    out["receiver_prior_med_count"] = df["receiver"].map(acc["prior_med_count"]).fillna(0).astype(int)
    return out[GOLD_FEATURES]


def gold(silver_df: pd.DataFrame, accounts: pd.DataFrame, with_graph: bool = True) -> pd.DataFrame:
    """Features por transação. Não lê nenhuma coluna de rótulo."""
    df = silver_df.sort_values(["ts", "tx_id"], kind="stable").reset_index(drop=True)
    feats = _features(df, accounts)
    base = df[["tx_id", "ts", "sender", "receiver", "amount", "channel", "device_id"]]
    out = pd.concat([base, feats], axis=1)
    if with_graph:
        flags = microbatch_flags(df)
        out = out.merge(flags, on="tx_id", how="left")
        out["graph_pattern"] = out["graph_pattern"].fillna("")
    else:
        out["graph_flag_ts"] = pd.NaT
        out["graph_pattern"] = ""
    return out
