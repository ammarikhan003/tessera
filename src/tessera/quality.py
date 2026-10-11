"""Data quality checks: row counts, unique OA codes, nulls, percentage ranges and sums.

Each check returns a list of human-readable failures (empty means it passed), so
they compose into one report instead of stopping at the first problem.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import pandas as pd

from tessera import config


class QualityError(Exception):
    """Raised when a dataset fails one or more quality checks."""


def check_row_count(df: pd.DataFrame, expected: int) -> list[str]:
    return [] if len(df) == expected else [f"expected {expected:,} rows, got {len(df):,}"]


def check_unique(df: pd.DataFrame, column: str) -> list[str]:
    dupes = df[column][df[column].duplicated()].unique()
    return [f"{len(dupes)} duplicated {column} values, e.g. {list(dupes[:5])}"] if len(dupes) else []


def check_no_nulls(df: pd.DataFrame, columns: Iterable[str] | None = None) -> list[str]:
    cols = list(columns) if columns is not None else list(df.columns)
    nulls = df[cols].isna().sum()
    return [f"{n} nulls in {col}" for col, n in nulls[nulls > 0].items()]


def check_percent_range(df: pd.DataFrame, columns: Iterable[str]) -> list[str]:
    failures = []
    for col in columns:
        bad = ((df[col] < 0) | (df[col] > 100)).sum()
        if bad:
            failures.append(f"{bad} values of {col} outside [0, 100]")
    return failures


def percent_group_deviation(df: pd.DataFrame, groups: Mapping[str, Sequence[str]]) -> pd.Series:
    """Largest absolute deviation from 100 of each group's row sums."""
    return pd.Series({g: (df[list(cols)].sum(axis=1) - 100).abs().max() for g, cols in groups.items()})


def check_percent_groups(
    df: pd.DataFrame, groups: Mapping[str, Sequence[str]], tol: float = config.PERCENT_SUM_TOLERANCE
) -> list[str]:
    failures = []
    for group, cols in groups.items():
        off = ((df[list(cols)].sum(axis=1) - 100).abs() > tol).sum()
        if off:
            failures.append(f"{off} rows where {group} percentages do not sum to 100 (tol {tol})")
    return failures


def percent_groups(specs: Iterable[config.TableSpec] = config.TABLE_SPECS) -> dict[str, list[str]]:
    return {spec.group: list(spec.features) for spec in specs}


def validate_features(
    df: pd.DataFrame,
    expected_rows: int = config.EXPECTED_LONDON_OAS,
    specs: Sequence[config.TableSpec] = config.TABLE_SPECS,
    tol: float = config.PERCENT_SUM_TOLERANCE,
) -> list[str]:
    """All step-2 checks on the OA feature table."""
    groups = percent_groups(specs)
    pct_cols = [c for cols in groups.values() for c in cols]
    failures = check_row_count(df, expected_rows)
    failures += check_unique(df, "OA21CD")
    failures += check_no_nulls(df)
    failures += check_percent_range(df, pct_cols)
    failures += check_percent_groups(df, groups, tol)
    if (df[config.DENSITY_FEATURE] <= 0).any():
        failures.append(f"non-positive values in {config.DENSITY_FEATURE}")
    return failures


def assert_valid(failures: list[str]) -> None:
    if failures:
        raise QualityError("quality checks failed:\n  " + "\n  ".join(failures))
