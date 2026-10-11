"""Compare Tessera segments against LOAC (7 supergroups, 16 groups).

Agreement is measured with the adjusted Rand index (ARI: do pairs of OAs that share
a LOAC class also share a Tessera segment?) and adjusted mutual information (AMI:
how much knowing one label tells you about the other). Both are already corrected
for chance, so ~0 means chance-level agreement and 1 means identical partitions up
to relabelling. The permutation baseline (Tessera labels shuffled across OAs) shows
the *spread* of chance scores, i.e. how far from 0 a score must be to be more than noise.

The k = 4..12 sweep against LOAC is DIAGNOSTIC ONLY. k was fixed at 8 in step 3b
from internal criteria (silhouette, stability, interpretability); choosing k to
maximise agreement with LOAC would tune the segmentation to the benchmark and make
the benchmark meaningless.

Agreement is not quality: LOAC's descriptions draw on ethnicity, religion, country
of birth, language, industry and housing variables that Tessera does not use.

Run with:  python -m tessera.benchmark
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # file output only; no display needed

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from sklearn.metrics import adjusted_mutual_info_score, adjusted_rand_score

from tessera import config
from tessera.segment import INK, INK_SECONDARY, SURFACE, _save, segment_name

SEQUENTIAL = LinearSegmentedColormap.from_list("blue", ["#fcfcfb", "#cde2fb", "#5598e7", "#184f95"])
LEVELS = {"supergroup": "SG", "group": "G"}


def load_labels() -> pd.DataFrame:
    """OA-level Tessera segment + LOAC supergroup/group; fails on any unmatched OA."""
    seg = pd.read_parquet(config.OA_SEGMENTS)[["OA21CD", "segment_id"]]
    loac = pd.read_csv(config.LOAC_LOOKUP_RAW, dtype=str, encoding="utf-8-sig").rename(columns={"OA": "OA21CD"})
    return join_labels(seg, loac)


def join_labels(seg: pd.DataFrame, loac: pd.DataFrame) -> pd.DataFrame:
    merged = seg.merge(loac, on="OA21CD", how="outer", validate="one_to_one", indicator=True)
    unmatched = merged["_merge"].ne("both").sum()
    if unmatched:
        raise ValueError(f"{unmatched} OAs present in only one of segments / LOAC")
    return merged.drop(columns="_merge")


def agreement(a: np.ndarray | pd.Series, b: np.ndarray | pd.Series) -> dict[str, float]:
    return {"ari": adjusted_rand_score(a, b), "ami": adjusted_mutual_info_score(a, b)}


def permutation_null(a: np.ndarray, b: np.ndarray, n: int, seed: int = config.RANDOM_SEED) -> pd.DataFrame:
    """ARI/AMI after shuffling `a` n times: the spread of scores produced by chance alone."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame([agreement(rng.permutation(a), b) for _ in range(n)])


def crosstabs(segments: pd.Series, loac: pd.Series) -> dict[str, pd.DataFrame]:
    """Counts, row % (each Tessera segment across LOAC) and column % (each LOAC class across segments)."""
    counts = pd.crosstab(segments, loac)
    return {
        "count": counts,
        "row_pct": counts.div(counts.sum(axis=1), axis=0).mul(100),
        "col_pct": counts.div(counts.sum(axis=0), axis=1).mul(100),
    }


def k_sweep(labels: pd.DataFrame) -> pd.DataFrame:
    """Diagnostic only: agreement of every sweep k with LOAC. Never used to choose k."""
    sweep = pd.read_parquet(config.KMEANS_SWEEP_LABELS).set_index("OA21CD").loc[labels["OA21CD"]]
    rows = []
    for col in sweep.columns:
        for level, code in LEVELS.items():
            rows.append({"k": int(col[1:]), "loac_level": level,
                         **agreement(sweep[col].to_numpy(), labels[code].to_numpy())})
    return pd.DataFrame(rows)


def _labelled(table: pd.DataFrame, names: dict[str, str]) -> pd.DataFrame:
    out = table.copy()
    out.index = [f"{s}. {segment_name(s)}" for s in out.index]
    out.columns = [f"{c}: {names[c]}" for c in out.columns]
    return out


def plot_crosstabs(tabs: dict[str, pd.DataFrame]) -> None:
    """Supergroup crosstab twice: row % (where each segment sits in LOAC) and column %."""
    fig, axes = plt.subplots(1, 2, figsize=(17, 6.8), facecolor=SURFACE)
    titles = {"row_pct": "Row %: share of each Tessera segment's OAs in each LOAC supergroup",
              "col_pct": "Column %: share of each LOAC supergroup's OAs in each Tessera segment"}
    for ax, key in zip(axes, ("row_pct", "col_pct")):
        t = tabs[key]
        ax.imshow(t.to_numpy(), cmap=SEQUENTIAL, vmin=0, vmax=100, aspect="auto")
        for i in range(t.shape[0]):
            for j in range(t.shape[1]):
                v = t.iat[i, j]
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8,
                        color=SURFACE if v > 55 else INK)
        ax.set_xticks(range(t.shape[1]), [f"{c}" for c in t.columns], fontsize=9, color=INK_SECONDARY)
        ax.set_yticks(range(t.shape[0]), [f"{s}. {segment_name(s)}" for s in t.index], fontsize=8.5,
                      color=INK_SECONDARY)
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_title(titles[key], loc="left", color=INK, fontsize=10)
        ax.set_xlabel("LOAC supergroup", color=INK_SECONDARY)
    key = "   ".join(f"{c} = {n}" for c, n in config.LOAC_SUPERGROUPS.items())
    fig.text(0.01, 0.01, key, color=INK_SECONDARY, fontsize=7.5, wrap=True)
    fig.suptitle("Tessera segments vs LOAC 2021 supergroups (% of OAs)", x=0.01, ha="left", color=INK, fontsize=12)
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    _save(fig, "loac_crosstab.png")


def main() -> None:
    labels = load_labels()
    seg = labels["segment_id"].to_numpy()
    print(f"OAs compared: {len(labels):,} (all matched)")

    rows, nulls = [], []
    for level, code in LEVELS.items():
        loac = labels[code].to_numpy()
        null = permutation_null(seg, loac, config.N_PERMUTATIONS)
        nulls.append(null.assign(loac_level=level))
        obs = agreement(seg, loac)
        rows.append({"loac_level": level, "n_loac_classes": labels[code].nunique(),
                     "ari": obs["ari"], "ami": obs["ami"],
                     "null_ari_mean": null["ari"].mean(), "null_ari_sd": null["ari"].std(),
                     "null_ari_max_abs": null["ari"].abs().max(),
                     "null_ami_mean": null["ami"].mean(), "null_ami_sd": null["ami"].std(),
                     "null_ami_max_abs": null["ami"].abs().max()})
        names = config.LOAC_SUPERGROUPS if level == "supergroup" else config.LOAC_GROUPS
        tabs = crosstabs(labels["segment_id"], labels[code])
        for norm, table in tabs.items():
            _labelled(table, names).to_csv(config.loac_crosstab_path(level, norm), float_format="%.2f")
        if level == "supergroup":
            plot_crosstabs(tabs)
        print(f"\n--- LOAC {level}s, row % (largest LOAC share per Tessera segment) ---")
        r = tabs["row_pct"]
        for s in r.index:
            top = r.loc[s].sort_values(ascending=False).head(2)
            print(f"  {s}. {segment_name(s):37} " + "; ".join(f"{c} {names[c]} {v:.1f}%" for c, v in top.items()))
        print(f"--- LOAC {level}s, column % (largest Tessera share per LOAC class) ---")
        c = tabs["col_pct"]
        for code_ in c.columns:
            s = c[code_].idxmax()
            print(f"  {code_} {names[code_]:48} -> {s}. {segment_name(s)} {c[code_].max():.1f}%")

    bench = pd.DataFrame(rows)
    null_all = pd.concat(nulls, ignore_index=True)
    sweep = k_sweep(labels)
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    bench.to_csv(config.LOAC_BENCHMARK_TABLE, index=False)
    null_all.to_csv(config.LOAC_NULL_TABLE, index=False)
    sweep.to_csv(config.LOAC_K_SWEEP_TABLE, index=False)

    pd.set_option("display.width", 170)
    print(f"\nAgreement with LOAC (k = {config.FINAL_K}; null = {config.N_PERMUTATIONS} shuffles, "
          f"seed {config.RANDOM_SEED}):")
    print(bench.round(4).to_string(index=False))
    print("\nk sweep vs LOAC (DIAGNOSTIC ONLY - k is not changed on this basis):")
    print(sweep.pivot(index="k", columns="loac_level", values=["ari", "ami"]).round(4).to_string())


if __name__ == "__main__":
    main()
