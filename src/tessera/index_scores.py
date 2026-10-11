"""Index scores (London average = 100) by segment and borough for a hypothetical mid-price gym.

Target customer: adults aged 25-44 in managerial/professional occupations (NS-SeC L1-L6).
Census tables are separate, so each OA's target count is estimated as
    residents aged 25-44 x (L1-L6 share of residents aged 16+),
which assumes age and NS-SeC are independent within an OA (~300 people).

Run with:  python -m tessera.index_scores
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # file output only; no display needed

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tessera import config
from tessera.segment import GRID, INK, INK_SECONDARY, SERIES, SURFACE, _save, _style, segment_name


def oa_components(features: pd.DataFrame) -> pd.DataFrame:
    """Per-OA counts: residents, residents 25-44, 16+ base, L1-L6 count and estimated target."""
    age_share = features[list(config.TARGET_AGE_FEATURES)].sum(axis=1) / 100
    nssec_share = features[list(config.TARGET_NSSEC_FEATURES)].sum(axis=1) / 100
    out = pd.DataFrame(
        {
            "residents": features["age_base"],
            "residents_25_44": features["age_base"] * age_share,
            "residents_16_plus": features["nssec_base"],
            "nssec_l1_l6": features["nssec_base"] * nssec_share,
        },
        index=features.index,
    )
    out["target_est"] = out["residents_25_44"] * nssec_share
    return out


def index_table(components: pd.DataFrame, keys: pd.Series) -> pd.DataFrame:
    """Aggregate OA counts by key; index = share vs London share x 100 (London row included)."""
    totals = components.groupby(keys.to_numpy()).sum()
    totals.loc["London"] = components.sum()
    london = totals.loc["London"]

    def rate(df: pd.DataFrame | pd.Series, num: str, den: str) -> pd.Series:
        return df[num] / df[den]

    table = pd.DataFrame(
        {
            "residents": totals["residents"],
            "target_est": totals["target_est"],
            "target_pct_of_residents": 100 * rate(totals, "target_est", "residents"),
            "pct_of_london_target": 100 * totals["target_est"] / london["target_est"],
            "index": 100 * rate(totals, "target_est", "residents") / rate(london, "target_est", "residents"),
            "age_25_44_index": 100 * rate(totals, "residents_25_44", "residents")
            / rate(london, "residents_25_44", "residents"),
            "nssec_l1_l6_index": 100 * rate(totals, "nssec_l1_l6", "residents_16_plus")
            / rate(london, "nssec_l1_l6", "residents_16_plus"),
        }
    )
    table["small_base"] = table["residents"] < config.SMALL_BASE_RESIDENTS
    return table


def segment_index(features: pd.DataFrame, segments: pd.Series) -> pd.DataFrame:
    table = index_table(oa_components(features), segments).rename_axis("segment_id").reset_index()
    table.insert(1, "segment_name", table["segment_id"].map(
        lambda s: "London" if s == "London" else segment_name(s)))
    return table


def borough_index(features: pd.DataFrame) -> pd.DataFrame:
    table = index_table(oa_components(features), features["LAD22CD"]).rename_axis("LAD22CD").reset_index()
    names = features.drop_duplicates("LAD22CD").set_index("LAD22CD")["LAD22NM"]
    table.insert(1, "LAD22NM", table["LAD22CD"].map(names).fillna("London"))
    return table


def plot_borough_extremes(boroughs: pd.DataFrame, n: int = config.INDEX_CHART_N) -> None:
    """Top and bottom n boroughs as index bars from 100 (log scale), labelled with volumes."""
    b = boroughs[boroughs["LAD22CD"] != "London"].sort_values("index", ascending=False)
    panels = [("Highest", b.head(n)), ("Lowest", b.tail(n))]
    fig, axes = plt.subplots(1, 2, figsize=(13, 0.42 * n + 1.8), facecolor=SURFACE)
    for ax, (label, part) in zip(axes, panels):
        _style(ax)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        part = part[::-1]
        names = [f"{nm}*" if small else nm for nm, small in zip(part["LAD22NM"], part["small_base"])]
        ax.barh(names, part["index"] - 100, left=100, color=SERIES, height=0.6)
        ax.axvline(100, color=INK_SECONDARY, linewidth=1)
        ax.set_xscale("log", base=2)
        ax.set_xlim(25, 400)
        ax.set_xticks([25, 50, 100, 200, 400], ["25", "50", "100", "200", "400"])
        for y, (idx, vol) in enumerate(zip(part["index"], part["target_est"])):
            x = idx * 1.05 if idx >= 100 else idx / 1.05
            ax.text(x, y, f"{idx:.0f}  ({vol / 1000:,.1f}k)", va="center",
                    ha="left" if idx >= 100 else "right", fontsize=8, color=INK_SECONDARY)
        ax.tick_params(axis="y", labelsize=9)
        ax.set_title(f"{label} {n} boroughs", loc="left", color=INK, fontsize=11)
        ax.set_xlabel("Index (London = 100), log scale", color=INK_SECONDARY)
    fig.suptitle("Mid-price gym target index by borough: residents aged 25-44 in managerial/professional "
                 "occupations\n(estimated target residents in brackets)",
                 x=0.01, y=0.99, ha="left", va="top", color=INK, fontsize=12)
    note = (f"* fewer than {config.SMALL_BASE_RESIDENTS:,} residents: index unstable. "
            "Estimate assumes age and NS-SeC are independent within each OA. Source: ONS Census 2021 (OGL v3.0).")
    fig.text(0.01, 0.01, note, color=INK_SECONDARY, fontsize=7.5)
    fig.subplots_adjust(left=0.14, right=0.98, top=0.84, bottom=0.14, wspace=0.42)
    _save(fig, "gym_index_boroughs.png")


def main() -> None:
    features = pd.read_parquet(config.OA_FEATURES).set_index("OA21CD")
    segments = pd.read_parquet(config.OA_SEGMENTS).set_index("OA21CD").loc[features.index, "segment_id"]

    seg = segment_index(features, segments)
    bor = borough_index(features)
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    seg.to_csv(config.GYM_INDEX_SEGMENTS_TABLE, index=False)
    bor.to_csv(config.GYM_INDEX_BOROUGHS_TABLE, index=False)
    plot_borough_extremes(bor)

    pd.set_option("display.width", 170)
    cols = ["residents", "target_est", "target_pct_of_residents", "pct_of_london_target", "index",
            "age_25_44_index", "nssec_l1_l6_index", "small_base"]
    print("By segment:")
    print(seg[["segment_id", "segment_name", *cols]].round(1).to_string(index=False))
    print("\nBy borough (sorted by index):")
    print(bor[["LAD22NM", *cols]].sort_values("index", ascending=False).round(1).to_string(index=False))
    b = bor[bor["LAD22CD"] != "London"]
    top10 = b.nlargest(10, "index")
    print(f"\nTop 10 boroughs by index hold {top10['pct_of_london_target'].sum():.1f}% of London's target "
          f"and {100 * top10['residents'].sum() / bor.loc[bor['LAD22CD'] == 'London', 'residents'].iloc[0]:.1f}% "
          "of residents")
    print(f"Index vs volume rank correlation (boroughs, Spearman): "
          f"{b['index'].corr(b['target_est'], method='spearman'):.3f}")
    print(f"\nWrote {config.GYM_INDEX_SEGMENTS_TABLE.name}, {config.GYM_INDEX_BOROUGHS_TABLE.name}, "
          "gym_index_boroughs.png")


if __name__ == "__main__":
    main()
