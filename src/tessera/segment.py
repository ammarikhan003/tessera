"""Standardise, PCA and k-means segmentation of output areas.

Step 3a (this module's `main`) is diagnostic only: feature correlations, PCA
explained variance, and a k-means sweep over config.K_RANGE with elbow and
silhouette plots. It deliberately does not choose k.

Step 3c (`main_final`) fits k = config.FINAL_K, saves OA labels and profiles each
segment against the London average.

Run with:  python -m tessera.segment            (3a diagnostics)
           python -m tessera.segment --final    (3c final segmentation)
"""

from __future__ import annotations

import sys
import textwrap
import time

import matplotlib

matplotlib.use("Agg")  # file output only; no display needed

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.preprocessing import StandardScaler

from tessera import config

# Plot styling (reference palette from the dataviz guidance, light surface).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3df"
SERIES = "#2a78d6"
DIVERGING = LinearSegmentedColormap.from_list("blue_gray_red", ["#2a78d6", "#f0efec", "#e34948"])


def feature_columns() -> list[str]:
    """Clustering features: all percentage features plus log density (never *_base or IDs)."""
    pct = [f for spec in config.TABLE_SPECS for f in spec.features]
    return pct + [config.LOG_DENSITY_FEATURE]


def feature_matrix(features: pd.DataFrame) -> pd.DataFrame:
    """OA-indexed feature matrix with density on a log10 scale."""
    X = features.set_index("OA21CD")
    X = X.assign(**{config.LOG_DENSITY_FEATURE: np.log10(X[config.DENSITY_FEATURE])})
    return X[feature_columns()]


def high_correlations(X: pd.DataFrame, threshold: float = config.CORRELATION_FLAG) -> pd.DataFrame:
    corr = X.corr()
    upper = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack()
    flagged = upper[upper.abs() >= threshold].rename("r").reset_index()
    flagged.columns = ["feature_a", "feature_b", "r"]
    return flagged.reindex(flagged["r"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def standardise(X: pd.DataFrame) -> np.ndarray:
    return StandardScaler().fit_transform(X)


def pca_variance_table(pca: PCA) -> pd.DataFrame:
    evr = pca.explained_variance_ratio_
    return pd.DataFrame(
        {
            "component": np.arange(1, len(evr) + 1),
            "eigenvalue": pca.explained_variance_,
            "explained_pct": 100 * evr,
            "cumulative_pct": 100 * np.cumsum(evr),
        }
    )


def n_components_for(cumulative_pct: pd.Series, threshold: float = config.PCA_VARIANCE_THRESHOLD) -> int:
    """Fewest components whose cumulative explained variance reaches threshold."""
    return int(np.argmax(cumulative_pct.to_numpy() >= 100 * threshold - 1e-9) + 1)


def kmeans_sweep(
    scores: np.ndarray,
    ks: range = config.K_RANGE,
    seed: int = config.RANDOM_SEED,
    n_init: int = config.KMEANS_N_INIT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit k-means for each k. Returns (metrics per k, labels with one column per k)."""
    rows, labels = [], {}
    for k in ks:
        start = time.perf_counter()
        km = KMeans(n_clusters=k, n_init=n_init, random_state=seed).fit(scores)
        sizes = np.bincount(km.labels_, minlength=k) / len(km.labels_)
        rows.append(
            {
                "k": k,
                "inertia": km.inertia_,
                "silhouette": silhouette_score(scores, km.labels_),
                "calinski_harabasz": calinski_harabasz_score(scores, km.labels_),
                "davies_bouldin": davies_bouldin_score(scores, km.labels_),
                "smallest_cluster_pct": 100 * sizes.min(),
                "largest_cluster_pct": 100 * sizes.max(),
                "seconds": time.perf_counter() - start,
            }
        )
        labels[f"k{k}"] = km.labels_
    return pd.DataFrame(rows), pd.DataFrame(labels)


# --- Final segmentation and profiles (step 3c) ------------------------------------


def pca_scores(X: pd.DataFrame) -> np.ndarray:
    """Standardise, then keep the fewest PCA components reaching the variance threshold."""
    Z = standardise(X)
    pca = PCA(random_state=config.RANDOM_SEED).fit(Z)
    n_keep = n_components_for(pca_variance_table(pca)["cumulative_pct"])
    return pca.transform(Z)[:, :n_keep]


def fit_segments(
    scores: np.ndarray,
    k: int = config.FINAL_K,
    seed: int = config.RANDOM_SEED,
    n_init: int = config.KMEANS_N_INIT,
) -> np.ndarray:
    return KMeans(n_clusters=k, n_init=n_init, random_state=seed).fit(scores).labels_


def segment_name(segment_id: int) -> str:
    return config.SEGMENT_NAMES.get(int(segment_id), f"Segment {segment_id}")


def relabel_by_size(labels: np.ndarray) -> np.ndarray:
    """Renumber clusters 1..k, largest first (ties by original label), so IDs are reproducible."""
    sizes = np.bincount(labels)
    order = sorted(range(len(sizes)), key=lambda c: (-sizes[c], c))
    mapping = {old: new for new, old in enumerate(order, start=1)}
    return np.array([mapping[c] for c in labels])


def feature_groups() -> dict[str, str]:
    """Percentage feature -> its Census table group (whose *_base column is the denominator)."""
    return {f: spec.group for spec in config.TABLE_SPECS for f in spec.features}


def weighted_shares(features: pd.DataFrame, segments: pd.Series) -> pd.DataFrame:
    """Population-weighted % per segment, plus a 'London' row.

    Each feature is sum(count) / sum(base) over the segment's OAs, i.e. the share of
    the segment's people (or households) in that category, not a mean of OA rates.
    """
    rows = {}
    for name, part in [*features.groupby(segments.to_numpy()), ("London", features)]:
        rows[name] = {
            f: (part[f] * part[f"{g}_base"]).sum() / part[f"{g}_base"].sum()
            for f, g in feature_groups().items()
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def segment_sizes(features: pd.DataFrame, segments: pd.Series) -> pd.DataFrame:
    g = features.groupby(segments.to_numpy())
    sizes = pd.DataFrame(
        {
            "n_oas": g.size(),
            "residents": g["age_base"].sum(),
            "households": g["hh_base"].sum(),
            "median_density_per_km2": g[config.DENSITY_FEATURE].median(),
        }
    )
    for col in ("n_oas", "residents", "households"):
        sizes.insert(sizes.columns.get_loc(col) + 1, f"pct_{col}", 100 * sizes[col] / sizes[col].sum())
    sizes.index.name = "segment_id"
    return sizes.reset_index()


def profile_table(features: pd.DataFrame, segments: pd.Series) -> pd.DataFrame:
    """Long table: segment x feature with segment %, London %, index (London = 100) and z.

    z is the gap in OA-level standard deviations, so features on different scales
    can share one colour scale. Density is a rate, so it is compared on medians of
    log10 density and gets no index.
    """
    shares = weighted_shares(features, segments)
    london = shares.loc["London"]
    oa_sd = features[list(feature_groups())].std()
    long = (
        shares.drop(index="London")
        .rename_axis("segment_id")
        .reset_index()
        .melt(id_vars="segment_id", var_name="feature", value_name="segment_pct")
    )
    long["group"] = long["feature"].map(feature_groups())
    long["london_pct"] = long["feature"].map(london)
    long["index"] = 100 * long["segment_pct"] / long["london_pct"]
    long["z"] = (long["segment_pct"] - long["london_pct"]) / long["feature"].map(oa_sd)

    density_values = features[config.DENSITY_FEATURE]
    seg_median = density_values.groupby(segments.to_numpy()).median()
    london_median = density_values.median()
    density = pd.DataFrame(
        {
            "segment_id": seg_median.index,
            "feature": config.DENSITY_FEATURE,
            "group": "density",
            "segment_median": seg_median.to_numpy(),
            "london_median": london_median,
            "z": np.log10(seg_median.to_numpy() / london_median) / np.log10(density_values).std(),
        }
    )
    return pd.concat([long, density], ignore_index=True)


def feature_label(feature: str) -> str:
    """'nssec_full_time_students' -> 'full time students', 'age_0_4' -> '0–4' (group shown separately)."""
    if feature == config.DENSITY_FEATURE:
        return "median persons per km²"
    group, rest = feature.split("_", 1)
    return rest.replace("_", "–" if group == "age" else " ")


# --- Figures --------------------------------------------------------------------


def _style(ax: plt.Axes) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _figure(ncols: int = 1, size: tuple[float, float] = (7, 4.2)) -> tuple[plt.Figure, np.ndarray]:
    fig, axes = plt.subplots(1, ncols, figsize=size, facecolor=SURFACE, squeeze=False)
    for ax in axes.ravel():
        _style(ax)
    return fig, axes.ravel()


def _save(fig: plt.Figure, name: str) -> None:
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(config.FIGURES_DIR / name, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def plot_correlations(X: pd.DataFrame) -> None:
    corr = X.corr()
    fig, ax = plt.subplots(figsize=(11, 9.5), facecolor=SURFACE)
    im = ax.imshow(corr, cmap=DIVERGING, vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr)), corr.columns, rotation=90, fontsize=7, color=INK_SECONDARY)
    ax.set_yticks(range(len(corr)), corr.columns, fontsize=7, color=INK_SECONDARY)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Pearson r", color=INK_SECONDARY)
    cbar.outline.set_visible(False)
    ax.set_title("Feature correlations, London OAs", loc="left", color=INK, fontsize=12)
    _save(fig, "feature_correlation_heatmap.png")


def plot_pca(table: pd.DataFrame, n_keep: int) -> None:
    fig, (left, right) = _figure(2, (11, 4.2))
    left.bar(table["component"], table["explained_pct"], color=SERIES, width=0.7)
    left.set_title("Variance explained per component", loc="left", color=INK, fontsize=11)
    left.set_xlabel("Principal component", color=INK_SECONDARY)
    left.set_ylabel("% of total variance", color=INK_SECONDARY)

    right.plot(table["component"], table["cumulative_pct"], color=SERIES, linewidth=2,
               marker="o", markersize=4)
    right.axhline(100 * config.PCA_VARIANCE_THRESHOLD, color=INK_SECONDARY, linewidth=1, linestyle="--")
    kept = table.loc[n_keep - 1, "cumulative_pct"]
    right.plot([n_keep], [kept], marker="o", markersize=9, color=SERIES, markeredgecolor=SURFACE,
               markeredgewidth=2)
    right.annotate(f"{n_keep} components: {kept:.1f}%", (n_keep, kept), xytext=(10, -18),
                   textcoords="offset points", color=INK, fontsize=9)
    right.set_title("Cumulative variance explained", loc="left", color=INK, fontsize=11)
    right.set_xlabel("Number of components", color=INK_SECONDARY)
    right.set_ylabel("% of total variance", color=INK_SECONDARY)
    right.set_ylim(0, 102)
    _save(fig, "pca_explained_variance.png")


def _plot_metric(metrics: pd.DataFrame, column: str, ylabel: str, title: str, name: str) -> None:
    fig, (ax,) = _figure()
    ax.plot(metrics["k"], metrics[column], color=SERIES, linewidth=2, marker="o", markersize=8,
            markeredgecolor=SURFACE, markeredgewidth=2)
    ax.set_xticks(metrics["k"])
    ax.set_xlabel("Number of clusters (k)", color=INK_SECONDARY)
    ax.set_ylabel(ylabel, color=INK_SECONDARY)
    ax.set_title(title, loc="left", color=INK, fontsize=11)
    _save(fig, name)


def plot_elbow(metrics: pd.DataFrame) -> None:
    _plot_metric(metrics, "inertia", "Within-cluster sum of squares",
                 "Elbow: k-means inertia by k", "kmeans_elbow.png")


def plot_silhouette(metrics: pd.DataFrame) -> None:
    _plot_metric(metrics, "silhouette", "Mean silhouette score",
                 "Silhouette score by k (higher is better separated)", "kmeans_silhouette.png")


def plot_profile_heatmap(profile: pd.DataFrame, sizes: pd.DataFrame) -> None:
    """Segments x features, coloured by z, annotated with the index (median for density)."""
    order = [f for spec in config.TABLE_SPECS for f in spec.features] + [config.DENSITY_FEATURE]
    z = profile.pivot(index="feature", columns="segment_id", values="z").loc[order]
    idx = profile.pivot(index="feature", columns="segment_id", values="index").loc[order]
    med = profile.pivot(index="feature", columns="segment_id", values="segment_median").loc[order]
    groups = profile.drop_duplicates("feature").set_index("feature")["group"].loc[order]

    clip = config.HEATMAP_Z_CLIP
    fig, ax = plt.subplots(figsize=(10, 14), facecolor=SURFACE)
    im = ax.imshow(z.clip(-clip, clip), cmap=DIVERGING, vmin=-clip, vmax=clip, aspect="auto")
    for i, feature in enumerate(order):
        for j, seg in enumerate(z.columns):
            text = (f"{med.loc[feature, seg] / 1000:.1f}k" if feature == config.DENSITY_FEATURE
                    else f"{idx.loc[feature, seg]:.0f}")
            colour = SURFACE if abs(z.loc[feature, seg]) > 0.6 * clip else INK
            ax.text(j, i, text, ha="center", va="center", fontsize=7, color=colour)

    ylabels = [f"{config.GROUP_LABELS.get(g, 'Density')}: {feature_label(f)}"
               for f, g in groups.items()]
    ax.set_yticks(range(len(order)), ylabels, fontsize=7.5, color=INK_SECONDARY)
    xlabels = [f"{s}\n{p:.1f}% OAs" for s, p in zip(sizes["segment_id"], sizes["pct_n_oas"])]
    ax.set_xticks(range(len(z.columns)), xlabels, fontsize=8, color=INK_SECONDARY)
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    breaks = np.flatnonzero(groups.to_numpy()[1:] != groups.to_numpy()[:-1]) + 0.5
    for b in breaks:
        ax.axhline(b, color=SURFACE, linewidth=3)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02, shrink=0.5)
    cbar.set_label("Gap from London (OA standard deviations)", color=INK_SECONDARY)
    cbar.outline.set_visible(False)
    ax.set_title("Segment profiles: index vs London (100 = average); density shows median persons/km²",
                 loc="left", color=INK, fontsize=11, pad=70)
    _save(fig, "segment_profile_heatmap.png")


def plot_top_features(profile: pd.DataFrame, top_n: int = config.PROFILE_TOP_N) -> None:
    """One panel per segment: its most distinctive features as index bars from 100 (log scale)."""
    pct = profile[profile["feature"] != config.DENSITY_FEATURE]
    segs = sorted(pct["segment_id"].unique())
    ncols = 2
    nrows = int(np.ceil(len(segs) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 3.0 * nrows), facecolor=SURFACE, squeeze=False)
    for ax, seg in zip(axes.ravel(), segs):
        _style(ax)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        top = pct[pct["segment_id"] == seg]
        top = top.reindex(top["z"].abs().sort_values(ascending=False).index).head(top_n)[::-1]
        labels = [f"{config.GROUP_LABELS[g]}: {feature_label(f)}" for f, g in zip(top["feature"], top["group"])]
        ax.barh(labels, top["index"] - 100, left=100, color=SERIES, height=0.6)
        ax.axvline(100, color=INK_SECONDARY, linewidth=1)
        ax.set_xscale("log", base=2)
        ax.set_xlim(12.5, 800)
        ax.set_xticks([25, 50, 100, 200, 400], ["25", "50", "100", "200", "400"])
        for y, (i, share) in enumerate(zip(top["index"], top["segment_pct"])):
            x = i * 1.08 if i >= 100 else i / 1.08
            ax.text(x, y, f"{i:.0f} ({share:.0f}%)", va="center", ha="left" if i >= 100 else "right",
                    fontsize=7.5, color=INK_SECONDARY)
        ax.tick_params(axis="y", labelsize=8)
        ax.set_title(f"{seg}. {segment_name(seg)}", loc="left", color=INK, fontsize=10)
    for ax in axes.ravel()[len(segs):]:
        ax.set_visible(False)
    fig.suptitle(f"Top {top_n} distinctive features per segment: index vs London = 100 "
                 "(segment share in brackets)", x=0.01, ha="left", color=INK, fontsize=12)
    fig.tight_layout()
    _save(fig, "segment_profiles_top_features.png")


def main_final() -> None:
    features = pd.read_parquet(config.OA_FEATURES)
    X = feature_matrix(features)
    features = features.set_index("OA21CD").loc[X.index].reset_index()

    raw = fit_segments(pca_scores(X))
    segments = pd.Series(relabel_by_size(raw), index=X.index, name="segment_id")

    out = features[["OA21CD", "LSOA21CD", "LAD22CD"]].assign(segment_id=segments.to_numpy())
    out["segment_name"] = out["segment_id"].map(segment_name)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(config.OA_SEGMENTS, index=False)

    sizes = segment_sizes(features, segments)
    profile = profile_table(features, segments)
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    sizes.to_csv(config.SEGMENT_SIZES_TABLE, index=False)
    profile.to_csv(config.SEGMENT_PROFILE_TABLE, index=False)
    plot_profile_heatmap(profile, sizes)
    plot_top_features(profile)

    sweep = pd.read_parquet(config.KMEANS_SWEEP_LABELS).set_index("OA21CD").loc[X.index]
    pd.set_option("display.width", 160)
    print(f"ARI vs step-3a sweep labels at k = {config.FINAL_K}: "
          f"{adjusted_rand_score(sweep[f'k{config.FINAL_K}'], raw):.4f}")
    print(f"\nSegment sizes:\n{sizes.round(2).to_string(index=False)}")
    for seg in sizes["segment_id"]:
        p = profile[(profile["segment_id"] == seg) & (profile["feature"] != config.DENSITY_FEATURE)]
        p = p.reindex(p["z"].abs().sort_values(ascending=False).index).head(12)
        d = profile[(profile["segment_id"] == seg) & (profile["feature"] == config.DENSITY_FEATURE)].iloc[0]
        print(f"\n=== Segment {seg} === median density {d['segment_median']:,.0f}/km² "
              f"(London {d['london_median']:,.0f}, z {d['z']:+.2f})")
        print(p[["feature", "segment_pct", "london_pct", "index", "z"]].round(2).to_string(index=False))
    print(f"\nWrote {config.OA_SEGMENTS.name}, {config.SEGMENT_SIZES_TABLE.name}, "
          f"{config.SEGMENT_PROFILE_TABLE.name} and two figures")


def main() -> None:
    features = pd.read_parquet(config.OA_FEATURES)
    X = feature_matrix(features)
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)

    flagged = high_correlations(X)
    flagged.to_csv(config.HIGH_CORRELATIONS_TABLE, index=False)
    plot_correlations(X)

    Z = standardise(X)
    pca = PCA(random_state=config.RANDOM_SEED).fit(Z)
    variance = pca_variance_table(pca)
    variance.to_csv(config.PCA_VARIANCE_TABLE, index=False)
    n_keep = n_components_for(variance["cumulative_pct"])
    plot_pca(variance, n_keep)

    scores = pca.transform(Z)[:, :n_keep]
    metrics, labels = kmeans_sweep(scores)
    metrics.to_csv(config.KMEANS_SWEEP_TABLE, index=False)
    labels.insert(0, "OA21CD", X.index)
    labels.to_parquet(config.KMEANS_SWEEP_LABELS, index=False)
    plot_elbow(metrics)
    plot_silhouette(metrics)

    pd.set_option("display.width", 140)
    print(f"Features: {X.shape[1]} on {X.shape[0]:,} OAs")
    print(f"\nPairs with |r| >= {config.CORRELATION_FLAG}: {len(flagged)}")
    print(flagged.round(3).to_string(index=False))
    print(f"\nPCA (first 15 components); eigenvalue > 1 count: {(variance['eigenvalue'] > 1).sum()}")
    print(variance.head(15).round(3).to_string(index=False))
    print(f"Kept {n_keep} components: {variance.loc[n_keep - 1, 'cumulative_pct']:.1f}% "
          f"(rule: fewest reaching {100 * config.PCA_VARIANCE_THRESHOLD:.0f}%)")
    print(f"\nk-means sweep (seed {config.RANDOM_SEED}, n_init {config.KMEANS_N_INIT}):")
    print(metrics.round(4).to_string(index=False))


if __name__ == "__main__":
    if "--final" in sys.argv[1:]:
        main_final()
    else:
        main()
