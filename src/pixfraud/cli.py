"""CLI: ``python -m pixfraud <comando>``."""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from pixfraud.cases import CaseStore, ClaudeSummarizer, DeterministicSummarizer, triage
from pixfraud.generator import GenConfig
from pixfraud.med import lifecycle_for_decision
from pixfraud.pipeline import run_pipeline
from pixfraud.report import write_report


def _cfg(a) -> GenConfig:
    return GenConfig(seed=a.seed, days=a.days, n_persons=a.persons)


def cmd_run(a) -> int:
    res = run_pipeline(_cfg(a))
    out = write_report(res, a.out)
    m = res["metrics"]
    print(f"transações={m['dataset']['n_transactions']} fraudes={m['dataset']['n_fraud']}")
    print(f"PR-AUC teste: {m['pr_auc_test']}")
    print(f"relatório em {out}")
    if a.cases:
        store = CaseStore(a.cases)
        dec = res["rule_result"].decisions.copy()
        dec["decision"] = res["combined"]["final_decision"]
        dec["ts"] = res["gold"]["ts"].astype(str)
        n = store.open_cases(dec, res["combined"]["final_score"])
        summ = ClaudeSummarizer() if a.llm else DeterministicSummarizer()
        t = triage(store, summ, limit=a.triage_limit)
        print(f"casos abertos={n} resumidos={t} ({summ.name}) em {a.cases}")
    return 0


def cmd_med(a) -> int:
    ts = pd.Timestamp("2026-01-10 10:00")
    for decision, outcome in (("APPROVE", None), ("BLOCK", None), ("REVIEW", "FALSE_POSITIVE"), ("REVIEW", "CONFIRMED_FRAUD")):
        c = lifecycle_for_decision("T-demo", decision, ts, outcome)
        print(f"{decision:8s}/{str(outcome):15s}: " + " -> ".join(s.value for s, *_ in c.history))
    print("Prazos usados são placeholders; simulação educacional (sem SPI/DICT).")
    return 0


def cmd_sweep(a) -> int:
    res = run_pipeline(_cfg(a))
    print(res["sweep"].to_string(index=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pixfraud", description="Laboratório educacional de decisão antifraude (dados sintéticos).")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("run", cmd_run), ("sweep", cmd_sweep)):
        s = sub.add_parser(name)
        s.add_argument("--seed", type=int, default=42)
        s.add_argument("--days", type=int, default=14)
        s.add_argument("--persons", type=int, default=400)
        if name == "run":
            s.add_argument("--out", default="reports")
            s.add_argument("--cases", default=None, help="caminho do SQLite de casos (opcional)")
            s.add_argument("--llm", action="store_true", help="usa ClaudeSummarizer (precisa de ANTHROPIC_API_KEY); consultivo")
            s.add_argument("--triage-limit", type=int, default=20)
        s.set_defaults(fn=fn)
    s = sub.add_parser("med-demo")
    s.set_defaults(fn=cmd_med)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
