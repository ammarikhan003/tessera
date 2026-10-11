"""Unit tests for wrangle.py on tiny synthetic tables shaped like the Nomis OA CSVs."""

from pathlib import Path

import pandas as pd
import pytest

from tessera import config, quality, wrangle

SPEC = config.TableSpec(
    table="tsX",
    group="cars",
    denominator="Total: All households",
    features={"cars_none": ["None"], "cars_some": ["One", "Two"]},
)


def counts(**rows: list[int]) -> pd.DataFrame:
    """rows: OA code -> [total, none, one, two]."""
    return pd.DataFrame.from_dict(
        rows, orient="index", columns=["Total: All households", "None", "One", "Two"]
    )


def test_clean_label_strips_prefix_and_suffix() -> None:
    assert wrangle.clean_label("Tenure of household: Owned: Owns outright; measures: Value") == (
        "Owned: Owns outright"
    )
    assert wrangle.clean_label("Age: Total") == "Total"
    assert wrangle.clean_label("OA21CD") == "OA21CD"


def test_read_oa_table_filters_and_cleans(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    pd.DataFrame(
        {
            "date": [2021, 2021],
            "geography": ["E1", "W1"],
            "geography code": ["E1", "W1"],
            "Age: Total": [10, 20],
        }
    ).to_csv(path, index=False)
    df = wrangle.read_oa_table(path, pd.Index(["E1"]))
    assert df.index.tolist() == ["E1"]
    assert df.columns.tolist() == ["Total"]


def test_table_to_percentages_uses_own_total_and_sums_to_100() -> None:
    out = wrangle.table_to_percentages(counts(A=[4, 1, 2, 1]), SPEC)
    assert out.loc["A", "cars_base"] == 4
    assert out.loc["A", "cars_none"] == pytest.approx(25.0)
    assert out.loc["A", "cars_some"] == pytest.approx(75.0)


def test_zero_denominator_gives_nan_not_inf() -> None:
    out = wrangle.table_to_percentages(counts(A=[0, 0, 0, 0]), SPEC)
    assert out[["cars_none", "cars_some"]].isna().all(axis=None)


def test_missing_label_raises() -> None:
    with pytest.raises(KeyError, match="Two"):
        wrangle.table_to_percentages(counts(A=[1, 1, 0, 0]).drop(columns="Two"), SPEC)


def _real_shaped_tables(oas: list[str]) -> dict[str, pd.DataFrame]:
    """One row per OA for every configured table, every category = 1."""
    tables = {}
    for spec in config.TABLE_SPECS:
        labels = [l for ls in spec.features.values() for l in ls]
        df = pd.DataFrame(1, index=oas, columns=labels)
        df.insert(0, spec.denominator, len(labels))
        tables[spec.table] = df
    tables[config.DENSITY_TABLE] = pd.DataFrame({config.DENSITY_LABEL: 1000.0}, index=oas)
    return tables


def _lookup(oas: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {"OA21CD": oas, "LSOA21CD": "L", "LAD22CD": "E09000001", "LAD22NM": "City of London"}
    )


def test_build_features_passes_quality_checks() -> None:
    oas = ["E1", "E2", "E3"]
    features, dropped = wrangle.build_features(_lookup(oas), _real_shaped_tables(oas))
    assert dropped.empty
    assert quality.validate_features(features, expected_rows=3) == []


def test_build_features_drops_and_logs_missing_and_zero_base() -> None:
    oas = ["E1", "E2", "E3"]
    tables = _real_shaped_tables(oas)
    tables["ts045"] = tables["ts045"].drop(index="E2")  # E2 missing from one table
    tables["ts054"].loc["E3"] = 0  # E3 has no households in tenure table
    features, dropped = wrangle.build_features(_lookup(oas), tables)
    assert features["OA21CD"].tolist() == ["E1"]
    reasons = dict(zip(dropped["OA21CD"], dropped["reason"]))
    assert reasons["E2"] == "missing from ts045"
    assert reasons["E3"].startswith("zero denominator or null in tenure_")
