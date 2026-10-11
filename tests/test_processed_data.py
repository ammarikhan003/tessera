"""Checks on the real data/processed/oa_features.parquet (skipped until wrangle.py has run)."""

import pandas as pd
import pytest

from tessera import config, quality

pytestmark = pytest.mark.skipif(
    not config.OA_FEATURES.exists(), reason="run `python -m tessera.wrangle` first"
)


@pytest.fixture(scope="module")
def features() -> pd.DataFrame:
    return pd.read_parquet(config.OA_FEATURES)


@pytest.fixture(scope="module")
def dropped() -> pd.DataFrame:
    return pd.read_csv(config.DROPPED_OAS, dtype=str)


def test_row_count_accounts_for_every_london_oa(features: pd.DataFrame, dropped: pd.DataFrame) -> None:
    assert len(features) + len(dropped) == config.EXPECTED_LONDON_OAS
    assert set(features["OA21CD"]).isdisjoint(dropped["OA21CD"])


def test_oa_codes_unique_and_london(features: pd.DataFrame) -> None:
    assert quality.check_unique(features, "OA21CD") == []
    assert features["LAD22CD"].str.startswith(config.LONDON_LAD_PREFIX).all()


def test_no_unexpected_nulls(features: pd.DataFrame) -> None:
    assert quality.check_no_nulls(features) == []


def test_percentage_groups_sum_to_100(features: pd.DataFrame) -> None:
    groups = quality.percent_groups()
    assert quality.check_percent_groups(features, groups) == []
    assert quality.check_percent_range(features, [c for cols in groups.values() for c in cols]) == []


def test_full_validation(features: pd.DataFrame, dropped: pd.DataFrame) -> None:
    expected = config.EXPECTED_LONDON_OAS - len(dropped)
    assert quality.validate_features(features, expected_rows=expected) == []
