import numpy as np
import pandas as pd
import pytest

from tessera import config, quality

GROUPS = {"g": ["a", "b"]}


def frame(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols)


def test_row_count() -> None:
    df = frame(x=[1, 2])
    assert quality.check_row_count(df, 2) == []
    assert quality.check_row_count(df, 3)


def test_unique() -> None:
    assert quality.check_unique(frame(OA21CD=["a", "b"]), "OA21CD") == []
    assert quality.check_unique(frame(OA21CD=["a", "a"]), "OA21CD")


def test_no_nulls() -> None:
    assert quality.check_no_nulls(frame(x=[1.0, 2.0])) == []
    assert quality.check_no_nulls(frame(x=[1.0, np.nan])) == ["1 nulls in x"]


def test_percent_range() -> None:
    assert quality.check_percent_range(frame(a=[0.0, 100.0]), ["a"]) == []
    assert quality.check_percent_range(frame(a=[-0.1, 100.1]), ["a"])


def test_percent_groups_within_and_beyond_tolerance() -> None:
    ok = frame(a=[60.0, 30.0], b=[40.0, 70.004])
    assert quality.check_percent_groups(ok, GROUPS, tol=0.01) == []
    bad = frame(a=[60.0], b=[39.0])
    assert quality.check_percent_groups(bad, GROUPS, tol=0.01)
    assert quality.percent_group_deviation(bad, GROUPS)["g"] == pytest.approx(1.0)


def test_percent_groups_match_config_features() -> None:
    groups = quality.percent_groups()
    assert list(groups) == [s.group for s in config.TABLE_SPECS]
    assert all(groups[s.group] == list(s.features) for s in config.TABLE_SPECS)


def test_assert_valid_raises_with_all_failures() -> None:
    quality.assert_valid([])
    with pytest.raises(quality.QualityError, match="first.*\n.*second"):
        quality.assert_valid(["first", "second"])
