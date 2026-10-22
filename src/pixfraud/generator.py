"""Gerador reprodutível de transações Pix/TED sintéticas com fraudes injetadas.

Devolve três tabelas separadas — ``transactions`` (sem rótulo), ``accounts`` e ``labels`` — para que nenhuma
etapa a jusante consiga ler o rótulo por engano.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

PATTERNS = (
    "mule",
    "fanout",
    "cycle",
    "chain",
    "velocity",
    "new_beneficiary",
    "device_takeover",
    "amount_anomaly",
)

_HOUR_W = np.array([1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 7, 5, 3, 2], dtype=float)
_HOUR_P = _HOUR_W / _HOUR_W.sum()


@dataclass(frozen=True)
class GenConfig:
    seed: int = 42
    n_persons: int = 400
    n_merchants: int = 12
    warmup_days: int = 3
    days: int = 14
    tx_per_person_day: float = 1.2
    start: str = "2026-01-05"
    legit_large_rate: float = 0.002
    n_young_legit: int = 15  # contas legítimas recém-abertas (geram falso positivo em PIX003/MED não)
    legit_young_large_rate: float = 0.004
    n_legit_crowd: int = 6  # vaquinha entre amigos: muitos remetentes -> 1 conta (falso positivo de MULE001)
    n_mule: int = 8
    n_fanout: int = 8
    n_cycle: int = 6
    n_chain: int = 6
    n_velocity: int = 8
    n_new_beneficiary: int = 10
    n_device_takeover: int = 10
    n_amount_anomaly: int = 10


def _sec(x: float | int) -> pd.Timedelta:
    return pd.Timedelta(seconds=int(x))


def generate(cfg: GenConfig = GenConfig()) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Gera (transactions, accounts, labels). Mesma ``cfg`` => mesmas tabelas."""
    rng = np.random.default_rng(cfg.seed)
    t_start = pd.Timestamp(cfg.start)
    total_days = cfg.warmup_days + cfg.days
    persons = [f"A{i:04d}" for i in range(cfg.n_persons)]
    merchants = [f"M{i:03d}" for i in range(cfg.n_merchants)]
    drops: list[str] = []

    def new_drop() -> str:
        drops.append(f"X{len(drops):04d}")
        return drops[-1]

    typical = {p: float(np.exp(rng.normal(np.log(150), 0.6))) for p in persons}
    young = persons[-cfg.n_young_legit :] if cfg.n_young_legit else []  # os últimos N são contas novas legítimas
    favorites: dict[str, list[str]] = {}
    pool = persons + merchants
    for p in persons:
        cand = [c for c in rng.choice(pool, size=6, replace=False) if c != p]
        favorites[p] = list(cand[:4])

    rows: list[dict] = []

    def add(t, s, r, a, ch, dev, label=0, pattern=""):
        rows.append(
            dict(ts=t, sender=s, receiver=r, amount=round(float(a), 2), channel=ch, device_id=dev,
                 label_fraud=int(label), fraud_pattern=pattern)
        )

    def home(p: str) -> str:
        return f"D-{p}-1"

    # ---- tráfego legítimo (inclui warm-up sem fraude) ----
    for day in range(total_days):
        for p in persons:
            for _ in range(int(rng.poisson(cfg.tx_per_person_day))):
                hour = int(rng.choice(24, p=_HOUR_P))
                t = t_start + pd.Timedelta(days=day, hours=hour, seconds=int(rng.integers(0, 3600)))
                u = rng.random()
                if u < 0.75:
                    r = favorites[p][int(rng.integers(0, len(favorites[p])))]
                elif u < 0.90:
                    r = merchants[int(rng.integers(0, len(merchants)))]
                else:
                    r = persons[int(rng.integers(0, len(persons)))]
                    if r == p:
                        r = favorites[p][0]
                a = max(1.0, typical[p] * float(np.exp(rng.normal(0, 0.5))))
                if rng.random() < cfg.legit_large_rate:
                    a = typical[p] * float(rng.uniform(8, 20))  # compra grande legítima (gera falso positivo)
                if young and rng.random() < cfg.legit_young_large_rate:
                    r = young[int(rng.integers(0, len(young)))]  # ex.: pagamento a quem abriu conta há pouco
                    if r == p:
                        r = favorites[p][0]
                    a = float(rng.uniform(2000, 6000))
                dev = home(p) if rng.random() < 0.97 else f"D-{p}-2"
                ch = "PIX" if rng.random() < 0.9 else "TED"
                add(t, p, r, a, ch, dev)

    def t0() -> pd.Timestamp:
        day = int(rng.integers(cfg.warmup_days, total_days - 1))
        hour = int(rng.choice(24, p=_HOUR_P))
        return t_start + pd.Timedelta(days=day, hours=hour, minutes=int(rng.integers(0, 50)))

    def person() -> str:
        return persons[int(rng.integers(0, len(persons)))]

    # ---- vaquinha legítima: 5-8 amigos pagam a mesma pessoa em ~20 min (rótulo 0) ----
    for _ in range(cfg.n_legit_crowd):
        host, base = person(), t0()
        for f in rng.choice(persons, size=int(rng.integers(5, 9)), replace=False):
            if f != host:
                add(base + _sec(rng.integers(0, 1200)), f, host, rng.uniform(40, 200), "PIX", home(f))

    mule_accounts: list[str] = []

    # ---- conta mula: fan-in de vítimas e dispersão rápida ----
    for _ in range(cfg.n_mule):
        mule = new_drop()
        mule_accounts.append(mule)
        outs = [new_drop() for _ in range(3)]
        base = t0()
        victims = rng.choice(persons, size=int(rng.integers(6, 11)), replace=False)
        ins = []
        for v in victims:
            a = float(np.clip(typical[v] * rng.uniform(3, 8), 800, 4000))
            t = base + _sec(rng.integers(0, 1500))
            add(t, v, mule, a, "PIX", home(v), 1, "mule")
            ins.append((t, a))
        t_last = max(t for t, _ in ins)
        total = sum(a for _, a in ins)
        for d in outs:
            add(t_last + _sec(rng.integers(120, 480)), mule, d, total * 0.31, "PIX", f"D-mule-{mule}", 1, "mule")

    # ---- fan-out: conta comprometida pulveriza para favorecidos novos ----
    for i in range(cfg.n_fanout):
        a_id, base = person(), t0()
        for _ in range(int(rng.integers(6, 10))):
            add(base + _sec(rng.integers(0, 600)), a_id, new_drop(), rng.uniform(300, 900), "PIX",
                f"D-evil-{i}", 1, "fanout")

    # ---- ciclo A->B->C->A ----
    for _ in range(cfg.n_cycle):
        ring = [new_drop() for _ in range(int(rng.integers(3, 5)))]
        a0, t = float(rng.uniform(2000, 6000)), t0()
        for k, s in enumerate(ring):
            add(t, s, ring[(k + 1) % len(ring)], a0 * (0.985**k), "PIX", f"D-ring-{s}", 1, "cycle")
            t = t + _sec(rng.integers(120, 300))

    # ---- triangulação / camadas: encaminhamento em cadeia ----
    for _ in range(cfg.n_chain):
        hops = int(rng.integers(4, 6))
        nodes = [person()] + [new_drop() for _ in range(hops)]
        a, t = float(rng.uniform(1500, 5000)), t0()
        for k in range(hops):
            dev = home(nodes[0]) if k == 0 else f"D-chain-{nodes[k]}"
            add(t, nodes[k], nodes[k + 1], a, "PIX", dev, 1, "chain")
            a *= 0.94
            t = t + _sec(rng.integers(120, 420))

    # ---- velocity: rajada de transações em poucos minutos ----
    for _ in range(cfg.n_velocity):
        p, base = person(), t0()
        recs = [person() for _ in range(3)]
        for _ in range(int(rng.integers(7, 11))):
            r = recs[int(rng.integers(0, 3))]
            if r == p:
                r = favorites[p][0]
            add(base + _sec(rng.integers(0, 240)), p, r, rng.uniform(150, 600), "PIX", home(p), 1, "velocity")

    # ---- novo favorecido com valor alto ----
    for _ in range(cfg.n_new_beneficiary):
        p = person()
        add(t0(), p, new_drop(), rng.uniform(5000, 12000), "PIX", home(p), 1, "new_beneficiary")

    # ---- troca de dispositivo (account takeover) ----
    for i in range(cfg.n_device_takeover):
        p = person()
        a = float(np.clip(typical[p] * rng.uniform(8, 20), 1500, 6000))
        add(t0(), p, favorites[p][0], a, "PIX", f"D-takeover-{i}", 1, "device_takeover")

    # ---- anomalia de valor ----
    for _ in range(cfg.n_amount_anomaly):
        p = person()
        a = max(1000.0, typical[p] * float(rng.uniform(12, 25)))
        add(t0(), p, favorites[p][1], a, "PIX", home(p), 1, "amount_anomaly")

    df = pd.DataFrame(rows).sort_values("ts", kind="stable").reset_index(drop=True)
    df.insert(0, "tx_id", [f"T{i:06d}" for i in range(len(df))])

    acc_rows = []
    for p in persons:
        age = int(rng.integers(1, 7)) if p in young else int(rng.integers(120, 3000))
        acc_rows.append((p, "person", age, int(rng.integers(1, 3)) if rng.random() < 0.01 else 0, typical[p]))
    for m in merchants:
        acc_rows.append((m, "merchant", int(rng.integers(365, 3000)), 0, 300.0))
    for d in drops:
        prior = int(rng.integers(2, 5)) if rng.random() < 0.4 else 0
        acc_rows.append((d, "drop", int(rng.integers(1, 6)), prior, 0.0))
    accounts = pd.DataFrame(acc_rows, columns=["account_id", "kind", "age_days", "prior_med_count", "typical_amount"])

    labels = df[["tx_id", "label_fraud", "fraud_pattern"]].copy()
    tx = df.drop(columns=["label_fraud", "fraud_pattern"])
    return tx, accounts, labels


def make_dirty(tx: pd.DataFrame, n_duplicates: int = 5, n_invalid: int = 5, seed: int = 7) -> pd.DataFrame:
    """Injeta duplicatas e linhas inválidas na camada bronze (para testar a quarentena do silver)."""
    rng = np.random.default_rng(seed)
    dup = tx.sample(n=min(n_duplicates, len(tx)), random_state=int(rng.integers(0, 10_000)))
    bad = tx.sample(n=min(n_invalid, len(tx)), random_state=int(rng.integers(0, 10_000))).copy()
    bad["tx_id"] = [f"BAD{i:03d}" for i in range(len(bad))]
    kinds = [0, 1, 2]
    for k, idx in enumerate(bad.index):
        kind = kinds[k % 3]
        if kind == 0:
            bad.loc[idx, "amount"] = -5.0
        elif kind == 1:
            bad.loc[idx, "receiver"] = None
        else:
            bad.loc[idx, "receiver"] = bad.loc[idx, "sender"]
    return pd.concat([tx, dup, bad], ignore_index=True)
