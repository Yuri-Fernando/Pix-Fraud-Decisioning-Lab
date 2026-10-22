import json

import pytest

from pixfraud.cli import main
from pixfraud.generator import PATTERNS
from pixfraud.medallion_spark import BackendUnavailable, run_spark
from pixfraud.report import build_html, build_markdown, write_report


def test_pipeline_metrics_are_consistent(pipe):
    m = pipe["metrics"]
    d = m["dataset"]
    assert d["n_transactions"] == len(pipe["gold"]) and d["n_fraud"] > 0
    assert d["n_train"] + d["n_test"] < d["n_transactions"]  # há faixa de purga
    assert {p["pattern"] for p in m["by_pattern"]} == set(PATTERNS)
    for sc in ("rules_only_all", "rules_only_test", "combined_test"):
        assert m[sc]["tp"] + m[sc]["fp"] == m[sc]["flagged"]
    assert m["pr_auc_test"]["combined"] > m["pr_auc_test"]["prevalence_test"]
    assert m["combined_test"]["recall"] >= m["rules_only_test"]["recall"] - 1e-9  # combinar nunca afrouxa


def test_every_flagged_transaction_by_rules_has_reason_codes_and_evidence(pipe):
    dec = pipe["rule_result"].decisions
    flagged = dec[dec["decision"] != "APPROVE"]
    assert len(flagged) > 0
    assert flagged["reason_codes"].map(len).min() >= 1
    assert flagged["evidence"].map(bool).all()


def test_report_files_are_written(pipe, tmp_path):
    write_report(pipe, tmp_path)
    for f in ("report.md", "report.html", "metrics.json", "rule_performance.csv", "figures/sweep_velocity.png", "figures/pr_curves.png"):
        assert (tmp_path / f).stat().st_size > 0, f
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "<table>" in html and "sem integração com SPI/DICT" in html
    assert json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))["dataset"]["n_fraud"] > 0


def test_markdown_states_synthetic_nature(pipe):
    md = build_markdown(pipe)
    assert "100% sintéticos" in md and "SPI/DICT" in md
    assert "<h1>" in build_html(md)


def test_cli_med_demo_runs(capsys):
    assert main(["med-demo"]) == 0
    out = capsys.readouterr().out
    assert "CONFIRMED_FRAUD" in out and "placeholders" in out


def test_cli_run_end_to_end_with_cases(tmp_path, capsys):
    db = tmp_path / "cases.sqlite"
    assert main(["run", "--days", "4", "--persons", "60", "--out", str(tmp_path / "rep"), "--cases", str(db), "--triage-limit", "3"]) == 0
    assert (tmp_path / "rep" / "report.md").exists() and db.exists()
    assert "casos abertos=" in capsys.readouterr().out


def test_spark_backend_reports_unavailability_instead_of_faking():
    try:
        import pyspark  # noqa: F401
    except ImportError:
        with pytest.raises(BackendUnavailable, match="pyspark"):
            run_spark("x.parquet", "delta_out")
    else:
        pytest.skip("pyspark instalado: a execução real do backend Spark não está coberta por este teste (NOT_RUN)")


def test_spark_backend_parity_with_pandas_is_not_run_here():
    pytest.importorskip("pyspark", reason="NOT_RUN: PySpark/Java compatível indisponível neste ambiente")
    pytest.skip("paridade Spark×pandas ainda não escrita")
