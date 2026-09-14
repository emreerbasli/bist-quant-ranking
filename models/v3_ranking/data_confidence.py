"""V4 data lineage and confidence checks for the V3.2 decision-support stack.

This module is deliberately read-only with respect to market, portfolio, and
model artefacts.  It neither changes ranking scores nor produces trading
instructions.  Its only job is to make the provenance and freshness of an
inference run auditable.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


DEFAULT_MAX_RAW_AGE_DAYS = 3
DEFAULT_MAX_FEATURE_AGE_DAYS = 3


@dataclass(frozen=True)
class DatasetCheck:
    symbol: str
    layer: str
    path: str
    latest_observation: Optional[str]
    age_days: Optional[int]
    status: str
    issues: tuple[str, ...]
    sha256: Optional[str]


@dataclass(frozen=True)
class DataConfidenceReport:
    as_of: str
    generated_at: str
    score: int
    status: str
    summary: str
    raw_coverage_pct: float
    feature_coverage_pct: float
    checks: tuple[DatasetCheck, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalise_timestamp(value: object) -> Optional[pd.Timestamp]:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    if getattr(timestamp, "tzinfo", None) is not None:
        timestamp = timestamp.tz_localize(None)
    return pd.Timestamp(timestamp).normalize()


def _extract_dates(frame: pd.DataFrame) -> pd.DatetimeIndex:
    if isinstance(frame.index, pd.DatetimeIndex):
        return pd.DatetimeIndex(frame.index).tz_localize(None) if frame.index.tz else frame.index
    for column in ("date", "Date", "tarih", "Tarih", "datetime", "Datetime"):
        if column in frame.columns:
            values = pd.to_datetime(frame[column], errors="coerce").dropna()
            return pd.DatetimeIndex(values)
    return pd.DatetimeIndex([])


def _check_parquet(
    symbol: str,
    layer: str,
    path: Path,
    as_of: pd.Timestamp,
    max_age_days: int,
) -> DatasetCheck:
    if not path.exists():
        return DatasetCheck(symbol, layer, str(path), None, None, "MISSING", ("dosya_yok",), None)

    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # corrupt or unsupported files must be surfaced, not hidden
        return DatasetCheck(symbol, layer, str(path), None, None, "ERROR", (f"okuma_hatasi:{type(exc).__name__}",), None)

    issues: list[str] = []
    dates = _extract_dates(frame)
    if len(dates) == 0:
        issues.append("tarih_alani_yok")
        latest = None
        age_days = None
    else:
        latest = pd.Timestamp(dates.max()).normalize()
        age_days = max(0, int((as_of - latest).days))
        if dates.duplicated().any():
            issues.append("tekrarli_tarih")

    close_column = next((name for name in ("close", "Close", "kapanis") if name in frame.columns), None)
    if close_column is not None:
        close = pd.to_numeric(frame[close_column], errors="coerce")
        if close.isna().all():
            issues.append("kapanis_tamamen_bos")
        elif (close.dropna() <= 0).any():
            issues.append("gecersiz_kapanis")

    if latest is None:
        status = "ERROR"
    elif age_days is not None and age_days > max_age_days:
        status = "STALE"
    elif issues:
        status = "WARNING"
    else:
        status = "OK"

    return DatasetCheck(
        symbol=symbol,
        layer=layer,
        path=str(path),
        latest_observation=latest.date().isoformat() if latest is not None else None,
        age_days=age_days,
        status=status,
        issues=tuple(issues),
        sha256=_sha256(path),
    )


def _infer_as_of(raw_dir: Path, symbols: Iterable[str]) -> pd.Timestamp:
    dates: list[pd.Timestamp] = []
    for symbol in symbols:
        path = raw_dir / f"{symbol.replace('.', '_')}.parquet"
        if not path.exists():
            continue
        try:
            extracted = _extract_dates(pd.read_parquet(path))
            if len(extracted):
                dates.append(pd.Timestamp(extracted.max()).normalize())
        except Exception:
            continue
    if not dates:
        raise ValueError("as_of belirlenemedi: okunabilir ham fiyat verisi yok.")
    return max(dates)


def build_data_confidence_report(
    raw_dir: Path,
    feature_dir: Path,
    symbols: Iterable[str],
    *,
    as_of: Optional[object] = None,
    max_raw_age_days: int = DEFAULT_MAX_RAW_AGE_DAYS,
    max_feature_age_days: int = DEFAULT_MAX_FEATURE_AGE_DAYS,
) -> DataConfidenceReport:
    """Audit raw and feature parquet inputs without changing any V3.2 output.

    ``as_of`` must be the run's known market date in production.  If omitted,
    the latest raw observation is used solely for a safe local audit.
    """
    symbols = tuple(symbols)
    if not symbols:
        raise ValueError("En az bir sembol gereklidir.")
    effective_as_of = _normalise_timestamp(as_of) if as_of is not None else _infer_as_of(raw_dir, symbols)
    if effective_as_of is None:
        raise ValueError("Geçerli bir as_of tarihi gereklidir.")

    checks: list[DatasetCheck] = []
    for symbol in symbols:
        stem = symbol.replace(".", "_")
        checks.append(_check_parquet(symbol, "raw_price", raw_dir / f"{stem}.parquet", effective_as_of, max_raw_age_days))
        checks.append(_check_parquet(symbol, "feature", feature_dir / f"{stem}.parquet", effective_as_of, max_feature_age_days))

    raw_checks = [check for check in checks if check.layer == "raw_price"]
    feature_checks = [check for check in checks if check.layer == "feature"]
    raw_coverage = 100.0 * sum(check.status in {"OK", "WARNING"} for check in raw_checks) / len(raw_checks)
    feature_coverage = 100.0 * sum(check.status in {"OK", "WARNING"} for check in feature_checks) / len(feature_checks)

    # Fixed operational policy, intentionally not calibrated on returns.
    penalty = sum(
        35 if check.status in {"MISSING", "ERROR"} else 20 if check.status == "STALE" else 5 if check.status == "WARNING" else 0
        for check in checks
    )
    score = max(0, min(100, round(100 - penalty / len(checks))))
    status = "GREEN" if score >= 90 else "AMBER" if score >= 70 else "RED"
    non_ok = [check for check in checks if check.status != "OK"]
    summary = (
        "Veri soyağacı ve güncellik kontrolleri normal."
        if not non_ok
        else f"{len(non_ok)} veri denetimi dikkat gerektiriyor; bu rapor al/sat sinyali değildir."
    )
    return DataConfidenceReport(
        as_of=effective_as_of.date().isoformat(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        score=score,
        status=status,
        summary=summary,
        raw_coverage_pct=round(raw_coverage, 2),
        feature_coverage_pct=round(feature_coverage, 2),
        checks=tuple(checks),
    )


def write_report_atomically(report: DataConfidenceReport, destination: Path) -> Path:
    """Persist an immutable run artefact using replace-on-success semantics."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(report.to_dict(), output, ensure_ascii=False, indent=2)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, destination)
    return destination
