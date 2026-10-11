import numpy as np
import pandas as pd

from tessera import config, tableau_export


def _inputs(n: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(5)
    f = pd.DataFrame({
        "OA21CD": [f"E{i:03d}" for i in range(n)],
        "LSOA21CD": "L1",
        "LAD22CD": ["E09000001"] * 4 + ["E09000002"] * (n - 4),
        "LAD22NM": ["A"] * 4 + ["B"] * (n - 4),
        config.DENSITY_FEATURE: 10.0 ** rng.uniform(3, 4.5, n),
    })
    for spec in config.TABLE_SPECS:
        f[f"{spec.group}_base"] = rng.integers(100, 400, n).astype(float)
        shares = rng.dirichlet(np.ones(len(spec.features)), n) * 100
        for i, feat in enumerate(spec.features):
            f[feat] = shares[:, i]
    seg = pd.DataFrame({"OA21CD": f["OA21CD"], "segment_id": np.arange(n) % 3 + 1})
    seg["segment_name"] = seg["segment_id"].map(lambda s: f"S{s}")
    return f, seg


def test_oa_table_one_row_per_oa_and_percentages_in_range() -> None:
    f, seg = _inputs()
    out = tableau_export.oa_table(f, seg)
    assert len(out) == len(f) and out["OA21CD"].is_unique
    pct = [c for spec in config.TABLE_SPECS for c in spec.features]
    assert out[pct].ge(0).all().all() and out[pct].le(100).all().all()
    assert (out["gym_target_est"] <= out["residents"]).all()


def test_profiles_table_is_segment_by_feature() -> None:
    f, seg = _inputs()
    out = tableau_export.profiles_table(f, seg["segment_id"])
    n_features = sum(len(spec.features) for spec in config.TABLE_SPECS)
    assert len(out) == 3 * n_features
    assert not out.duplicated(["segment_id", "feature"]).any()
    assert out["topic"].notna().all()


def test_index_table_has_segments_and_boroughs_without_london() -> None:
    f, seg = _inputs()
    out = tableau_export.index_table(f, seg["segment_id"])
    assert sorted(out["level"].unique()) == ["borough", "segment"]
    assert (out["geo_id"] != "London").all()
    for level in ("segment", "borough"):
        assert np.isclose(out.loc[out["level"] == level, "pct_of_london_target"].sum(), 100)
