import numpy as np
import pandas as pd
import pytest

from tessera import config, segment


def _features(n: int = 6) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    data = {"OA21CD": [f"E{i}" for i in range(n)], "age_base": 100, config.DENSITY_FEATURE: 10.0 ** rng.uniform(2, 5, n)}
    for spec in config.TABLE_SPECS:
        data[f"{spec.group}_base"] = 100
        for f in spec.features:
            data[f] = rng.uniform(0, 100, n)
    return pd.DataFrame(data)


def test_feature_matrix_logs_density_and_excludes_bases() -> None:
    df = _features()
    X = segment.feature_matrix(df)
    assert list(X.columns) == segment.feature_columns()
    assert not any(c.endswith("_base") for c in X.columns)
    assert config.DENSITY_FEATURE not in X.columns
    np.testing.assert_allclose(X[config.LOG_DENSITY_FEATURE], np.log10(df[config.DENSITY_FEATURE]))


def test_high_correlations_flags_pairs_once() -> None:
    a = np.arange(10.0)
    X = pd.DataFrame({"a": a, "b": 2 * a + 1, "c": np.sin(a)})
    out = segment.high_correlations(X, threshold=0.9)
    assert out[["feature_a", "feature_b"]].values.tolist() == [["a", "b"]]
    assert out["r"].iloc[0] == pytest.approx(1.0)


def test_n_components_for_threshold() -> None:
    cum = pd.Series([50.0, 79.9, 80.0, 95.0])
    assert segment.n_components_for(cum, 0.80) == 3
    assert segment.n_components_for(cum, 0.50) == 1


def test_kmeans_sweep_is_deterministic_and_finds_blobs() -> None:
    rng = np.random.default_rng(1)
    centres = np.array([[0, 0], [10, 0], [0, 10]])
    pts = np.vstack([c + rng.normal(0, 0.3, (30, 2)) for c in centres])
    m1, l1 = segment.kmeans_sweep(pts, ks=range(2, 5), seed=7, n_init=5)
    m2, l2 = segment.kmeans_sweep(pts, ks=range(2, 5), seed=7, n_init=5)
    pd.testing.assert_frame_equal(l1, l2)
    assert m1.loc[m1["silhouette"].idxmax(), "k"] == 3
    assert list(l1.columns) == ["k2", "k3", "k4"]


def test_relabel_by_size_orders_largest_first() -> None:
    labels = np.array([2, 2, 2, 0, 1, 1])
    np.testing.assert_array_equal(segment.relabel_by_size(labels), [1, 1, 1, 3, 2, 2])


def _counts_features() -> tuple[pd.DataFrame, pd.Series]:
    """Two segments with unequal bases, built so each table's % sum to 100 per OA."""
    rng = np.random.default_rng(2)
    n = 8
    data = {"OA21CD": [f"E{i}" for i in range(n)], config.DENSITY_FEATURE: 10.0 ** rng.uniform(2, 5, n)}
    for spec in config.TABLE_SPECS:
        data[f"{spec.group}_base"] = rng.integers(50, 500, n)
        shares = rng.dirichlet(np.ones(len(spec.features)), n) * 100
        for i, f in enumerate(spec.features):
            data[f] = shares[:, i]
    df = pd.DataFrame(data)
    return df, pd.Series([1, 1, 1, 2, 2, 2, 2, 2])


def test_weighted_shares_are_count_ratios_and_sum_to_100() -> None:
    df, seg = _counts_features()
    shares = segment.weighted_shares(df, seg)
    part = df[seg.to_numpy() == 1]
    expected = (part["age_0_4"] * part["age_base"]).sum() / part["age_base"].sum()
    assert shares.loc[1, "age_0_4"] == pytest.approx(expected)
    for spec in config.TABLE_SPECS:
        np.testing.assert_allclose(shares[list(spec.features)].sum(axis=1), 100)


def test_profile_index_is_100_when_segment_equals_london() -> None:
    df, _ = _counts_features()
    profile = segment.profile_table(df, pd.Series(np.ones(len(df), dtype=int)))
    pct = profile[profile["feature"] != config.DENSITY_FEATURE]
    np.testing.assert_allclose(pct["index"], 100)
    np.testing.assert_allclose(profile["z"], 0, atol=1e-12)


def test_segment_sizes_cover_every_oa() -> None:
    df, seg = _counts_features()
    sizes = segment.segment_sizes(df, seg)
    assert sizes["n_oas"].sum() == len(df)
    assert sizes["pct_n_oas"].sum() == pytest.approx(100)
    assert sizes["residents"].sum() == df["age_base"].sum()
