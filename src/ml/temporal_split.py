"""Chronological, time-aware dataset splitting and strict leakage prevention for Stage I."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger("kitchenpilot.ml.temporal_split")


@dataclass
class LeakageCheckResult:
    """Audit of future temporal and session leakage across split partitions."""
    passed: bool
    future_timestamp_in_train: int = 0
    query_session_overlap: int = 0
    anomalies: List[str] = field(default_factory=list)


def verify_temporal_leakage(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    timestamp_col: str = "impression_timestamp",
) -> LeakageCheckResult:
    """Verify strictly monotonic chronological ordering across partitions with zero lookahead."""
    anomalies: List[str] = []
    future_in_train = 0
    session_overlap = 0

    if train_df.empty or test_df.empty:
        return LeakageCheckResult(passed=True)

    # 1. Query/Session disjointness
    if "session_id" in train_df.columns:
        train_sessions = set(train_df["session_id"].dropna())
        val_sessions = set(val_df["session_id"].dropna()) if not val_df.empty else set()
        test_sessions = set(test_df["session_id"].dropna())

        overlap_tv = train_sessions.intersection(val_sessions)
        overlap_tt = train_sessions.intersection(test_sessions)
        overlap_vt = val_sessions.intersection(test_sessions)

        total_overlap = len(overlap_tv) + len(overlap_tt) + len(overlap_vt)
        session_overlap = total_overlap
        if total_overlap > 0:
            anomalies.append(
                f"Session leakage: {len(overlap_tt)} sessions span train and test partitions."
            )

    # 2. Monotonic timestamp verification
    if timestamp_col in train_df.columns:
        train_max = pd.to_datetime(train_df[timestamp_col]).max()

        if not val_df.empty and timestamp_col in val_df.columns:
            val_min = pd.to_datetime(val_df[timestamp_col]).min()
            if train_max > val_min:
                anomalies.append(f"Temporal inversion: Train max ({train_max}) > Validation min ({val_min}).")
                future_in_train += 1

        if timestamp_col in test_df.columns:
            test_min = pd.to_datetime(test_df[timestamp_col]).min()
            if train_max > test_min:
                anomalies.append(f"Temporal inversion: Train max ({train_max}) > Test min ({test_min}).")
                future_in_train += 1

    passed = (len(anomalies) == 0 and future_in_train == 0 and session_overlap == 0)
    return LeakageCheckResult(
        passed=passed,
        future_timestamp_in_train=future_in_train,
        query_session_overlap=session_overlap,
        anomalies=anomalies,
    )


def chronological_query_split(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    timestamp_col: str = "impression_timestamp",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, str]]:
    """Partition query sessions chronologically without breaking query boundaries or leaking future data.
    
    Returns:
        (train_df, val_df, test_df, cutoffs_dict)
    """
    if df.empty or "session_id" not in df.columns or timestamp_col not in df.columns:
        return df, pd.DataFrame(columns=df.columns), pd.DataFrame(columns=df.columns), {}

    # Determine earliest timestamp per query session
    session_times = (
        df.groupby("session_id")[timestamp_col]
        .min()
        .reset_index()
    )
    session_times["dt"] = pd.to_datetime(session_times[timestamp_col], errors="coerce")
    session_times = session_times.sort_values(by="dt").reset_index(drop=True)

    n_sessions = len(session_times)
    train_end = int(n_sessions * train_ratio)
    val_end = int(n_sessions * (train_ratio + val_ratio))

    train_sess = set(session_times.iloc[:train_end]["session_id"])
    val_sess = set(session_times.iloc[train_end:val_end]["session_id"])
    test_sess = set(session_times.iloc[val_end:]["session_id"])

    train_df = df[df["session_id"].isin(train_sess)].copy()
    val_df = df[df["session_id"].isin(val_sess)].copy()
    test_df = df[df["session_id"].isin(test_sess)].copy()

    cutoffs = {
        "train_sessions": str(len(train_sess)),
        "val_sessions": str(len(val_sess)),
        "test_sessions": str(len(test_sess)),
        "train_end_timestamp": str(train_df[timestamp_col].max()) if not train_df.empty else "N/A",
        "val_end_timestamp": str(val_df[timestamp_col].max()) if not val_df.empty else "N/A",
        "test_end_timestamp": str(test_df[timestamp_col].max()) if not test_df.empty else "N/A",
    }

    # Verify leakage immediately
    leakage = verify_temporal_leakage(train_df, val_df, test_df, timestamp_col=timestamp_col)
    if not leakage.passed:
        raise ValueError(f"Temporal leakage detected during chronological split: {'; '.join(leakage.anomalies)}")

    return train_df, val_df, test_df, cutoffs
