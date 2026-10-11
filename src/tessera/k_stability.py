"""Stability check and smallest-cluster profile for the shortlisted k values.

Step 3b, diagnostic only: the sweep metrics barely separate k = 7 and k = 8, so
this asks whether each solution is reproducible (across seeds and across 80%
subsamples of OAs) and what the ~1% cluster that appears from k = 6 actually is.

Run with:  python -m tessera.k_stability
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score

from tessera import config
from tessera.segment import feature_matrix, pca_scores, standardise


def fit_labels(scores: np.ndarray, k: int, seed: int) -> KMeans:
    return KMeans(n_clusters=k, n_init=config.KMEANS_N_INIT, random_state=seed).fit(scores)


def seed_stability(scores: np.ndarray, k: int, seeds: tuple[int, ...]) -> list[float]:
    """Pairwise ARI between full-data fits that differ only in random seed."""
    labels = [fit_labels(scores, k, s).labels_ for s in seeds]
    return [adjusted_rand_score(a, b) for a, b in combinations(labels, 2)]


def subsample_stability(
    scores: np.ndarray, k: int, reference: np.ndarray, seeds: tuple[int, ...], fraction: float
) -> list[float]:
    """Refit on random subsamples, assign every OA to the nearest new centroid, ARI vs reference."""
    n = len(scores)
    aris = []
    for s in seeds:
        rows = np.random.default_rng(s).choice(n, size=int(fraction * n), replace=False)
        km = fit_labels(scores[rows], k, s)
        aris.append(adjusted_rand_score(reference, km.predict(scores)))
    return aris


def summarise(values: list[float]) -> dict[str, float]:
    return {"mean": float(np.mean(values)), "min": float(np.min(values)), "max": float(np.max(values))}


def profile_cluster(X: pd.DataFrame, Z: np.ndarray, mask: np.ndarray) -> pd.DataFrame:
    """Per-feature cluster mean vs London mean, ranked by standardised gap (z)."""
    profile = pd.DataFrame(
        {
            "cluster_mean": X[mask].mean(),
            "london_mean": X.mean(),
            "z": Z[mask].mean(axis=0),
        }
    )
    return profile.reindex(profile["z"].abs().sort_values(ascending=False).index)


def jaccard(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / (a | b).sum())


def main() -> None:
    features = pd.read_parquet(config.OA_FEATURES)
    X = feature_matrix(features)
    boroughs = features.set_index("OA21CD").loc[X.index, "LAD22NM"]
    Z = standardise(X)
    scores = pca_scores(X)

    rows, profiles, small_masks = [], [], {}
    for k in config.K_SHORTLIST:
        reference = fit_labels(scores, k, config.RANDOM_SEED).labels_
        seed_ari = summarise(seed_stability(scores, k, config.STABILITY_SEEDS))
        sub_ari = summarise(
            subsample_stability(scores, k, reference, config.STABILITY_SEEDS, config.SUBSAMPLE_FRACTION)
        )
        rows.append({"k": k, **{f"seed_ari_{m}": v for m, v in seed_ari.items()},
                     **{f"subsample_ari_{m}": v for m, v in sub_ari.items()}})

        sizes = np.bincount(reference, minlength=k)
        small = int(sizes.argmin())
        mask = reference == small
        small_masks[k] = mask
        profile = profile_cluster(X, Z, mask)
        profiles.append(profile.assign(k=k, n_oas=int(mask.sum())).rename_axis("feature").reset_index())

        print(f"\n=== k = {k} ===")
        print(f"Cluster sizes (OAs): {sorted(sizes.tolist(), reverse=True)}")
        print(f"Seed ARI (pairwise, {len(config.STABILITY_SEEDS)} seeds): "
              + ", ".join(f"{m} {v:.3f}" for m, v in seed_ari.items()))
        print(f"Subsample ARI ({config.SUBSAMPLE_FRACTION:.0%} of OAs, vs seed {config.RANDOM_SEED}): "
              + ", ".join(f"{m} {v:.3f}" for m, v in sub_ari.items()))
        print(f"\nSmallest cluster: {mask.sum()} OAs ({100 * mask.mean():.2f}%)")
        print("Top boroughs:")
        print(boroughs[mask].value_counts().head(8).to_string())
        print("\nMost distinctive features (z = mean standardised gap from London):")
        print(profile.head(10).round(3).to_string())

    if len(small_masks) == 2:
        a, b = small_masks.values()
        print(f"\nJaccard overlap of smallest clusters at k = {config.K_SHORTLIST}: {jaccard(a, b):.3f}")

    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(config.K_STABILITY_TABLE, index=False)
    pd.concat(profiles).to_csv(config.SMALLEST_CLUSTER_PROFILE_TABLE, index=False)
    print(f"\nWrote {config.K_STABILITY_TABLE.name} and {config.SMALLEST_CLUSTER_PROFILE_TABLE.name}")


if __name__ == "__main__":
    main()
