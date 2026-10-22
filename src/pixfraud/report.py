"""Relatório estático (Markdown + HTML + PNG) a partir do resultado do pipeline."""

from __future__ import annotations

import html
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import precision_recall_curve  # noqa: E402


def _fmt(v):
    if isinstance(v, float):
        return "n/d" if v != v else f"{v:.3f}"
    return str(v)


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_sem dados_\n"
    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = ["| " + " | ".join(_fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, sep, *body]) + "\n"


def plot_sweep(sweep: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(sweep["false_positive"], sweep["fraud_capture_rate"], marker="o")
    for _, r in sweep.iterrows():
        ax.annotate(f"≥{int(r['value'])} tx/5min", (r["false_positive"], r["fraud_capture_rate"]),
                    textcoords="offset points", xytext=(6, 6), fontsize=8)
    ax.set_xlabel("falsos positivos (nº de transações)")
    ax.set_ylabel("captura de valor fraudulento")
    ax.set_title("VELOCITY001 — captura × falso positivo por limiar")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_pr(result: dict, path: Path) -> None:
    ml, comb, res = result["ml"], result["combined"], result["rule_result"]
    test, y = ml["test_mask"], ml["y"]
    fig, ax = plt.subplots(figsize=(6, 4))
    for name, score in (("ML", ml["proba"]), ("regras", res.decisions["rule_score"]), ("combinado", comb["final_score"])):
        p, r, _ = precision_recall_curve(y[test], score[test])
        ax.plot(r, p, label=name)
    ax.axhline(y[test].mean(), color="gray", ls="--", label="prevalência")
    ax.set_xlabel("recall")
    ax.set_ylabel("precisão")
    ax.set_title("Curva precisão×recall no período de teste (dados sintéticos)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def build_markdown(result: dict) -> str:
    m = result["metrics"]
    d = m["dataset"]
    pr = m["pr_auc_test"]
    dec = pd.DataFrame(
        [{"cenário": k, **{c: v[c] for c in ("flagged", "tp", "fp", "precision", "recall", "block_precision",
                                              "fraud_value_captured_rate", "false_positive_rate")}}
         for k, v in (("regras (todo o período)", m["rules_only_all"]), ("regras (teste)", m["rules_only_test"]),
                      ("combinado (teste)", m["combined_test"]))]
    )
    perf = result["rule_performance"].copy()
    top = result["combined"].join(result["gold"][["tx_id", "sender", "amount"]], rsuffix="_g")
    top = top[top["final_decision"] != "APPROVE"].sort_values("final_score", ascending=False).head(10)
    top = top[["tx_id", "sender", "amount", "final_score", "final_decision"]]
    lines = [
        "# Relatório — Pix-Fraud-Decisioning-Lab",
        "",
        "> Dados 100% sintéticos; rótulos vêm do injetor de fraudes. Os números demonstram o pipeline, não "
        "desempenho em produção. Simulação educacional, sem integração com SPI/DICT.",
        "",
        f"Regras: v{m['rules_version']} · seed {m['config']['seed']}",
        "",
        "## Conjunto de dados",
        md_table(pd.DataFrame([{
            "transações": d["n_transactions"], "fraudes": d["n_fraud"], "taxa de fraude": d["fraud_rate"],
            "quarentena (silver)": d["n_quarantine"], "treino": d["n_train"], "teste": d["n_test"],
            "fraudes no teste": d["n_fraud_test"]}])),
        "## PR-AUC no período de teste (split temporal com purga)",
        md_table(pd.DataFrame([{"ML": pr["ml_only"], "regras": pr["rules_only"], "combinado": pr["combined"],
                                "prevalência (linha de base)": pr["prevalence_test"]}])),
        "## Decisões",
        md_table(dec),
        "## Recall por padrão de fraude",
        md_table(pd.DataFrame(m["by_pattern"])),
        "## Desempenho por regra (todo o período)",
        md_table(perf),
        "## Varredura de limiar — VELOCITY001.min_tx_5m",
        md_table(result["sweep"]),
        "![varredura](figures/sweep_velocity.png)",
        "",
        "## Curva precisão×recall",
        "![pr](figures/pr_curves.png)",
        "",
        "## Grafo",
        f"Transações sinalizadas pelo grafo: {m['graph']['n_flagged']} · precisão: {_fmt(m['graph']['precision'])} · "
        f"atraso mediano de detecção: {_fmt(m['graph']['median_detection_delay_s'])} s (alerta retrospectivo em micro-batch).",
        "",
        "## 10 maiores scores sinalizados",
        md_table(top),
    ]
    return "\n".join(lines)


def build_html(markdown: str) -> str:
    out, table, in_table = [], [], False

    def flush():
        nonlocal table
        if not table:
            return
        rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in table if not set(r.replace("|", "").strip()) <= set("-")]
        t = "<table>" + "".join(
            "<tr>" + "".join(f"<{'th' if i == 0 else 'td'}>{html.escape(c)}</{'th' if i == 0 else 'td'}>" for c in row) + "</tr>"
            for i, row in enumerate(rows)
        ) + "</table>"
        out.append(t)
        table = []

    for line in markdown.splitlines():
        if line.startswith("|"):
            table.append(line)
            continue
        flush()
        if line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("!["):
            src = line[line.index("(") + 1 : -1]
            out.append(f'<img src="{html.escape(src)}" width="520">')
        elif line.startswith("> "):
            out.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line.strip():
            out.append(f"<p>{html.escape(line)}</p>")
    flush()
    css = "body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem}table{border-collapse:collapse;margin:1rem 0}td,th{border:1px solid #ccc;padding:4px 8px;font-size:13px}th{background:#f2f2f2}blockquote{background:#fff7e6;padding:8px 12px;border-left:4px solid #c8742a}"
    return f"<!doctype html><html lang='pt-BR'><meta charset='utf-8'><title>Pix-Fraud-Decisioning-Lab</title><style>{css}</style><body>{''.join(out)}</body></html>"


def write_report(result: dict, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    plot_sweep(result["sweep"], out / "figures" / "sweep_velocity.png")
    plot_pr(result, out / "figures" / "pr_curves.png")
    md = build_markdown(result)
    (out / "report.md").write_text(md, encoding="utf-8")
    (out / "report.html").write_text(build_html(md), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps(result["metrics"], indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    result["rule_performance"].to_csv(out / "rule_performance.csv", index=False)
    return out
