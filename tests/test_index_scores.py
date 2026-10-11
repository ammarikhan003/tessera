import numpy as np
import pandas as pd
import pytest

from tessera import config, index_scores


def _features() -> pd.DataFrame:
    rng = np.random.default_rng(4)
    n = 12
    df = pd.DataFrame(
        {
            "age_base": rng.integers(150, 500, n).astype(float),
            "nssec_base": rng.integers(100, 400, n).astype(float),
            "LAD22CD": ["E09000001"] * 2 + ["E09000002"] * 10,
            "LAD22NM": ["Small"] * 2 + ["Big"] * 10,
        },
        index=[f"E{i}" for i in range(n)],
    )
    for f in (*config.TARGET_AGE_FEATURES, *config.TARGET_NSSEC_FEATURES):
        df[f] = rng.uniform(5, 30, n)
    return df


def test_target_never_exceeds_residents_25_44() -> None:
    comp = index_scores.oa_components(_features())
    assert (comp["target_est"] <= comp["residents_25_44"]).all()
    assert (comp["target_est"] >= 0).all()


def test_london_index_is_100_and_volumes_sum() -> None:
    df = _features()
    comp = index_scores.oa_components(df)
    seg = pd.Series(np.arange(len(df)) % 3, index=df.index)
    for table in (index_scores.index_table(comp, seg), index_scores.index_table(comp, df["LAD22CD"])):
        london = table.loc["London"]
        assert london[["index", "age_25_44_index", "nssec_l1_l6_index"]].tolist() == pytest.approx([100] * 3)
        parts = table.drop(index="London")
        assert parts["target_est"].sum() == pytest.approx(london["target_est"])
        assert parts["pct_of_london_target"].sum() == pytest.approx(100)


def test_index_is_share_ratio() -> None:
    df = _features()
    comp = index_scores.oa_components(df)
    table = index_scores.index_table(comp, df["LAD22CD"])
    big = comp[df["LAD22CD"] == "E09000002"].sum()
    expected = 100 * (big["target_est"] / big["residents"]) / (comp["target_est"].sum() / comp["residents"].sum())
    assert table.loc["E09000002", "index"] == pytest.approx(expected)


def test_small_base_flag() -> None:
    df = _features()
    table = index_scores.index_table(index_scores.oa_components(df), df["LAD22CD"])
    assert table.loc["E09000001", "small_base"]  # 2 OAs, far below the threshold
