import sys
from pathlib import Path
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from models.v3_ranking.data_confidence import build_data_confidence_report, write_report_atomically


def _write_parquet(directory: Path, symbol: str, dates: list[str], closes: list[float]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"date": pd.to_datetime(dates), "close": closes})
    frame.to_parquet(directory / f"{symbol.replace('.', '_')}.parquet", index=False)


def test_green_report_for_complete_current_inputs(tmp_path: Path) -> None:
    raw, feature = tmp_path / "raw", tmp_path / "features"
    for symbol in ("AAA.IS", "BBB.IS"):
        _write_parquet(raw, symbol, ["2026-09-07"], [10.0])
        _write_parquet(feature, symbol, ["2026-09-07"], [10.0])

    report = build_data_confidence_report(raw, feature, ["AAA.IS", "BBB.IS"], as_of="2026-09-07")

    assert report.status == "GREEN"
    assert report.score == 100
    assert report.raw_coverage_pct == 100.0
    assert all(check.sha256 for check in report.checks)


def test_missing_and_stale_inputs_lower_confidence_without_changing_data(tmp_path: Path) -> None:
    raw, feature = tmp_path / "raw", tmp_path / "features"
    _write_parquet(raw, "AAA.IS", ["2026-08-20"], [10.0])
    _write_parquet(feature, "AAA.IS", ["2026-09-07"], [10.0])

    report = build_data_confidence_report(raw, feature, ["AAA.IS", "BBB.IS"], as_of="2026-09-07")

    assert report.status == "AMBER"
    assert report.score < 100
    assert any(check.status == "STALE" for check in report.checks)
    assert any(check.status == "MISSING" for check in report.checks)


def test_report_is_written_as_json_atomically(tmp_path: Path) -> None:
    raw, feature = tmp_path / "raw", tmp_path / "features"
    _write_parquet(raw, "AAA.IS", ["2026-09-07"], [10.0])
    _write_parquet(feature, "AAA.IS", ["2026-09-07"], [10.0])
    report = build_data_confidence_report(raw, feature, ["AAA.IS"], as_of="2026-09-07")

    output = write_report_atomically(report, tmp_path / "reports" / "confidence.json")

    assert output.exists()
    assert '"status": "GREEN"' in output.read_text(encoding="utf-8")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        tpath = Path(td)
        print("Running test_green_report_for_complete_current_inputs...")
        test_green_report_for_complete_current_inputs(tpath / "t1")
        print("Running test_missing_and_stale_inputs_lower_confidence_without_changing_data...")
        test_missing_and_stale_inputs_lower_confidence_without_changing_data(tpath / "t2")
        print("Running test_report_is_written_as_json_atomically...")
        test_report_is_written_as_json_atomically(tpath / "t3")
    print("✅ ALL DATA CONFIDENCE TESTS PASSED!")
