import pandas as pd
import pytest

from pixfraud.generator import GenConfig
from pixfraud.pipeline import run_pipeline

SMALL = GenConfig(
    seed=1, n_persons=80, warmup_days=2, days=6, n_young_legit=5, n_legit_crowd=2,
    n_mule=3, n_fanout=3, n_cycle=3, n_chain=3, n_velocity=3,
    n_new_beneficiary=3, n_device_takeover=3, n_amount_anomaly=3,
)

# linha de transação que NÃO dispara nenhuma regra (base para testes de regra)
DEFAULTS = dict(
    tx_id="T1", amount=100.0, is_new_beneficiary=False, amount_ratio=1.0, receiver_age_days=1000,
    sender_tx_count_5m=1, new_device=False, receiver_fan_in_30m=1, sender_inflow_senders_30m=0,
    sender_outflow_ratio_15m=0.0, sender_fan_out_15m=1, graph_pattern="", receiver_prior_med_count=0,
)


def row(**kw) -> pd.DataFrame:
    return pd.DataFrame([{**DEFAULTS, **kw}])


def txs(rows) -> pd.DataFrame:
    """rows: (tx_id, minuto, sender, receiver, amount)."""
    base = pd.Timestamp("2026-01-10 10:00")
    return pd.DataFrame(
        [dict(tx_id=i, ts=base + pd.Timedelta(minutes=m), sender=s, receiver=r, amount=a) for i, m, s, r, a in rows]
    )


@pytest.fixture(scope="session")
def small_cfg():
    return SMALL


@pytest.fixture(scope="session")
def pipe():
    return run_pipeline(SMALL)
