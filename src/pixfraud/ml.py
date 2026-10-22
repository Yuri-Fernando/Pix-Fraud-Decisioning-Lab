"""Terceiro sinal: classificador supervisionado com avaliação temporal (sem vazamento)."""

from __future__ import annotations

import os
from dataclasses import dataclass

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "4")  # evita a detecção de núcleos por subprocesso (lenta no Windows)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import average_precision_score  # noqa: E402
from threadpoolctl import threadpool_limits  # noqa: E402

ML_FEATURES = [
    "amount_log",
    "amount_ratio",
    "sender_tx_count_5m",
    "sender_tx_count_1h",
    "sender_fan_out_15m",
    "receiver_fan_in_30m",
    "sender_inflow_senders_30m",
    "sender_outflow_ratio_15m",
    "is_new_beneficiary",
    "new_device",
    "receiver_age_days",
    "receiver_prior_med_count",
    "hour",
    "is_ted",
]


@dataclass(frozen=True)
class SplitConfig:
    train_end_q: float = 0.60  # treino: ts <= quantil 60%
    test_start_q: float = 0.70  # teste: ts > quantil 70% (faixa 60-70% é descartada como purga)


def design_matrix(gold: pd.DataFrame) -> pd.DataFrame:
    """Matriz de features. Não inclui rótulo, flags de grafo nem identificadores."""
    x = pd.DataFrame(index=gold.index)
    x["amount_log"] = np.log1p(gold["amount"])
    x["is_ted"] = (gold["channel"] == "TED").astype(int)
    for c in ML_FEATURES:
        if c not in x:
            x[c] = gold[c].astype(float)
    return x[ML_FEATURES]


def temporal_split(gold: pd.DataFrame, cfg: SplitConfig = SplitConfig()) -> tuple[pd.Series, pd.Series]:
    cut_train = gold["ts"].quantile(cfg.train_end_q)
    cut_test = gold["ts"].quantile(cfg.test_start_q)
    train = gold["ts"] <= cut_train
    test = gold["ts"] > cut_test
    assert not (train & test).any()
    return train, test


def train_eval(gold: pd.DataFrame, labels: pd.DataFrame, seed: int = 42, cfg: SplitConfig = SplitConfig()) -> dict:
    """Treina no passado, avalia no futuro. Devolve modelo, probabilidades (todas as linhas) e PR-AUC do teste."""
    y = gold[["tx_id"]].merge(labels[["tx_id", "label_fraud"]], on="tx_id", how="left")["label_fraud"].fillna(0).astype(int)
    train, test = temporal_split(gold, cfg)
    x = design_matrix(gold)
    model = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, random_state=seed)
    # em máquinas com muitos núcleos o OpenMP padrão fica ~3x mais lento neste tamanho de dado
    with threadpool_limits(limits=2):
        model.fit(x[train], y[train])
        proba = pd.Series(model.predict_proba(x)[:, 1], index=gold.index, name="ml_proba")
    pr = float(average_precision_score(y[test], proba[test])) if y[test].sum() > 0 else float("nan")
    return {
        "model": model,
        "proba": proba,
        "train_mask": train,
        "test_mask": test,
        "y": y,
        "pr_auc_test": pr,
        "test_prevalence": float(y[test].mean()),
        "n_train": int(train.sum()),
        "n_test": int(test.sum()),
    }
