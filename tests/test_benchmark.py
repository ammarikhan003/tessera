import numpy as np
import pandas as pd
import pytest

from tessera import benchmark

SHUFFLE_SEED = 123
CHANCE_TOLERANCE = 0.01  # |ARI|, |AMI| for shuffled labels on 5,000 points


def test_identical_partitions_score_one_even_when_renumbered() -> None:
    a = np.repeat([0, 1, 2, 3], 50)
    b = np.repeat([7, 3, 9, 1], 50)  # same grouping, different IDs
    scores = benchmark.agreement(a, b)
    assert scores["ari"] == pytest.approx(1.0)
    assert scores["ami"] == pytest.approx(1.0)


def test_shuffled_labels_score_near_zero() -> None:
    rng = np.random.default_rng(SHUFFLE_SEED)
    a = rng.integers(0, 8, 5000)
    b = rng.integers(0, 7, 5000)
    scores = benchmark.agreement(a, b)
    assert abs(scores["ari"]) < CHANCE_TOLERANCE
    assert abs(scores["ami"]) < CHANCE_TOLERANCE


def test_permutation_null_is_reproducible_and_centred_on_zero() -> None:
    a = np.repeat(np.arange(8), 300)
    b = np.repeat(np.arange(6), 400)
    n1 = benchmark.permutation_null(a, b, n=20, seed=SHUFFLE_SEED)
    n2 = benchmark.permutation_null(a, b, n=20, seed=SHUFFLE_SEED)
    pd.testing.assert_frame_equal(n1, n2)
    assert n1["ari"].abs().max() < CHANCE_TOLERANCE
    assert n1["ami"].abs().max() < CHANCE_TOLERANCE


def test_crosstab_rows_and_columns_each_sum_to_100() -> None:
    seg = pd.Series([1, 1, 2, 2, 2, 3])
    loac = pd.Series(["A", "B", "A", "A", "C", "C"])
    tabs = benchmark.crosstabs(seg, loac)
    np.testing.assert_allclose(tabs["row_pct"].sum(axis=1), 100)
    np.testing.assert_allclose(tabs["col_pct"].sum(axis=0), 100)
    assert tabs["count"].to_numpy().sum() == len(seg)


def test_join_fails_on_unmatched_oa() -> None:
    seg = pd.DataFrame({"OA21CD": ["E1", "E2"], "segment_id": [1, 2]})
    loac = pd.DataFrame({"OA21CD": ["E1", "E3"], "G": ["A1", "B1"], "SG": ["A", "B"]})
    with pytest.raises(ValueError, match="only one of"):
        benchmark.join_labels(seg, loac)
