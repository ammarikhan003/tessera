"""Tidy CSVs and GeoJSON for the Tableau Public dashboard (step 7).

Writes to data/processed/tableau/ (gitignored; rerun to reproduce):
  oa_segments_features.csv  one row per OA: codes, segment, counts, all features, gym target
  segment_profiles.csv      long: one row per segment x feature, with segment sizes repeated
  index_scores.csv          long: gym index for segments and boroughs, `level` says which
  oa_boundaries.geojson     OA polygons (WGS84), joined to the OA CSV on OA21CD
  boroughs.geojson          borough outlines

Run after `segment --final`, `maps` and `index_scores`:  python -m tessera.tableau_export
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from tessera import config, index_scores, segment


def oa_table(features: pd.DataFrame, segments: pd.DataFrame) -> pd.DataFrame:
    """Wide OA table: identifiers, segment, base counts, density, % features, gym target estimate."""
    pct = [f for spec in config.TABLE_SPECS for f in spec.features]
    out = features[["OA21CD", "LSOA21CD", "LAD22CD", "LAD22NM"]].merge(
        segments[["OA21CD", "segment_id", "segment_name"]], on="OA21CD", how="inner", validate="one_to_one"
    )
    out["residents"] = features["age_base"].to_numpy()
    out["households"] = features["hh_base"].to_numpy()
    out[config.DENSITY_FEATURE] = features[config.DENSITY_FEATURE].to_numpy()
    out[pct] = features[pct].to_numpy()
    out["gym_target_est"] = index_scores.oa_components(features)["target_est"].to_numpy()
    # Two decimals is far finer than Census disclosure noise and halves the file size.
    return out.round({**dict.fromkeys(pct, 2), config.DENSITY_FEATURE: 1, "gym_target_est": 2})


def profiles_table(features: pd.DataFrame, segment_ids: pd.Series) -> pd.DataFrame:
    """Long segment x feature profile with readable labels and segment sizes on every row."""
    profile = segment.profile_table(features, segment_ids)
    profile = profile[profile["feature"] != config.DENSITY_FEATURE].drop(
        columns=["segment_median", "london_median"]
    )
    profile["topic"] = profile["group"].map(config.GROUP_LABELS)
    profile["feature_label"] = profile["feature"].map(segment.feature_label)
    order = {f: i for i, f in enumerate(f for spec in config.TABLE_SPECS for f in spec.features)}
    profile["feature_order"] = profile["feature"].map(order)
    sizes = segment.segment_sizes(features, segment_ids)
    out = profile.merge(sizes, on="segment_id", how="left", validate="many_to_one")
    out.insert(1, "segment_name", out["segment_id"].map(segment.segment_name))
    cols = ["segment_id", "segment_name", "topic", "feature", "feature_label", "feature_order",
            "segment_pct", "london_pct", "index", "z", "n_oas", "pct_n_oas", "residents",
            "pct_residents", "households", "pct_households", "median_density_per_km2"]
    return out[cols].sort_values(["segment_id", "feature_order"]).reset_index(drop=True)


def index_table(features: pd.DataFrame, segment_ids: pd.Series) -> pd.DataFrame:
    """Segment and borough gym indices stacked; the London reference rows are dropped (index = 100)."""
    seg = index_scores.segment_index(features, segment_ids).rename(
        columns={"segment_id": "geo_id", "segment_name": "geo_name"})
    bor = index_scores.borough_index(features).rename(columns={"LAD22CD": "geo_id", "LAD22NM": "geo_name"})
    out = pd.concat([seg.assign(level="segment"), bor.assign(level="borough")], ignore_index=True)
    out = out[out["geo_id"] != "London"]
    out["geo_id"] = out["geo_id"].astype(str)
    return out[["level", "geo_id", "geo_name", *[c for c in out.columns if c not in ("level", "geo_id", "geo_name")]]]


def main() -> None:
    for path in (config.OA_SEGMENTS, config.OA_BOUNDARIES_GEOJSON, config.BOROUGHS_GEOJSON):
        if not path.exists():
            raise SystemExit(f"Missing {path}; run segment --final and maps first")

    features = pd.read_parquet(config.OA_FEATURES)
    segments = pd.read_parquet(config.OA_SEGMENTS)
    features = features.set_index("OA21CD").loc[segments["OA21CD"]].reset_index()
    segment_ids = segments["segment_id"].reset_index(drop=True)

    config.TABLEAU_DIR.mkdir(parents=True, exist_ok=True)
    tables = {
        config.TABLEAU_OA_CSV: oa_table(features, segments),
        config.TABLEAU_PROFILES_CSV: profiles_table(features, segment_ids),
        config.TABLEAU_INDEX_CSV: index_table(features, segment_ids),
    }
    for path, table in tables.items():
        table.to_csv(path, index=False, encoding="utf-8")
        print(f"{path.name}: {len(table):,} rows x {table.shape[1]} cols, {path.stat().st_size / 1e6:.2f} MB")
    for src in (config.OA_BOUNDARIES_GEOJSON, config.BOROUGHS_GEOJSON):
        dst = Path(shutil.copy2(src, config.TABLEAU_DIR / src.name))
        print(f"{src.name}: copied ({dst.stat().st_size / 1e6:.2f} MB)")
    print(f"\nAll Tableau inputs in {config.TABLEAU_DIR}")


if __name__ == "__main__":
    main()
