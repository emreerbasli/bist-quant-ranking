"""Shared temporal contracts for research-only validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class LabelInterval:
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    label_start: pd.Timestamp
    label_end: pd.Timestamp
    horizon_sessions: int


def build_label_interval(
    calendar: pd.DatetimeIndex,
    signal_date: pd.Timestamp,
    horizon_sessions: int,
) -> LabelInterval:
    """Create a next-session-entry label spanning exactly H return sessions."""
    if horizon_sessions <= 0:
        raise ValueError("horizon_sessions must be positive")
    cal = pd.DatetimeIndex(calendar).sort_values().unique()
    signal = pd.Timestamp(signal_date)
    pos = cal.searchsorted(signal)
    if pos >= len(cal) or cal[pos] != signal:
        raise ValueError("signal_date must be an exact trading session")
    entry_pos = pos + 1
    end_pos = entry_pos + horizon_sessions
    if end_pos >= len(cal):
        raise ValueError("calendar does not contain the completed horizon")
    return LabelInterval(
        signal_date=signal,
        entry_date=cal[entry_pos],
        label_start=cal[entry_pos],
        label_end=cal[end_pos],
        horizon_sessions=horizon_sessions,
    )


def purged_training_mask(
    observations: Iterable[LabelInterval],
    validation_or_test_start: pd.Timestamp,
) -> list[bool]:
    """Keep observations with labels completed strictly before the next fold."""
    boundary = pd.Timestamp(validation_or_test_start)
    return [obs.label_end < boundary for obs in observations]


def assert_no_label_overlap(
    observations: Iterable[LabelInterval],
    validation_or_test_start: pd.Timestamp,
) -> None:
    boundary = pd.Timestamp(validation_or_test_start)
    leaking = [obs for obs in observations if obs.label_end >= boundary]
    if leaking:
        raise AssertionError(f"{len(leaking)} training labels overlap the next fold")
