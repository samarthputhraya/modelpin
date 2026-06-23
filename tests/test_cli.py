"""End-to-end CLI tests. The `check` flow runs fully offline through FakeProvider
with the bundled demo fixtures — no network, no API keys — and must produce the
PR-style report and a CI-failing exit code on a real regression.
"""

from pathlib import Path

from typer.testing import CliRunner

from modelpin.cli import app

REPO = Path(__file__).resolve().parents[1]
FIXTURES = str(REPO / "examples" / "traces" / "demo_traces.json")
SCEN = str(REPO / "examples" / "scenarios")
CONFIG = str(REPO / "examples" / "modelpin.yaml")

runner = CliRunner()


def test_version():
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0
    assert "modelpin" in r.output


def test_scan_detects_the_example_dependency():
    r = runner.invoke(app, ["scan", str(REPO / "examples")])
    assert r.exit_code == 0
    assert "claude-opus-4-6" in r.output


def test_init_scaffolds_config_and_scenarios(tmp_path):
    r = runner.invoke(app, ["init", str(tmp_path)])
    assert r.exit_code == 0
    assert (tmp_path / "modelpin.yaml").exists()
    assert (tmp_path / "scenarios").is_dir()
    assert list((tmp_path / "scenarios").glob("*.json"))


def test_end_to_end_check_detects_regressions_offline(tmp_path):
    store = str(tmp_path / ".modelpin")
    base = runner.invoke(
        app,
        [
            "baseline",
            "--provider",
            "fake",
            "--fixtures",
            FIXTURES,
            "--model",
            "claude-opus-4-6",
            "--scenarios-dir",
            SCEN,
            "--config",
            CONFIG,
            "--store-dir",
            store,
            "--runs",
            "5",
        ],
    )
    assert base.exit_code == 0, base.output
    assert "Baseline recorded" in base.output

    chk = runner.invoke(
        app,
        [
            "check",
            "--to",
            "claude-opus-4-7",
            "--from",
            "claude-opus-4-6",
            "--provider",
            "fake",
            "--fixtures",
            FIXTURES,
            "--scenarios-dir",
            SCEN,
            "--config",
            CONFIG,
            "--store-dir",
            store,
            "--runs",
            "5",
        ],
    )
    # two scenarios regress (tool-call + refusal) -> CI-failing exit code
    assert chk.exit_code == 1, chk.output
    assert "refund_request" in chk.output
    assert "angry_customer" in chk.output

    report = (tmp_path / ".modelpin" / "last-report.md").read_text(encoding="utf-8")
    assert "REGRESSIONS" in report
    assert "invoice_parse" in report  # the format-drift minor change


def test_check_without_baseline_fails_clearly(tmp_path):
    r = runner.invoke(
        app,
        [
            "check",
            "--to",
            "x",
            "--from",
            "y",
            "--provider",
            "fake",
            "--scenarios-dir",
            SCEN,
            "--config",
            CONFIG,
            "--store-dir",
            str(tmp_path / "empty"),
        ],
    )
    assert r.exit_code == 1
    assert "baseline" in r.output.lower()
