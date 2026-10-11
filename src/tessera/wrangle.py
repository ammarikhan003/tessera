"""Filter Census 2021 OA tables to London, convert counts to percentages, join on OA code.

Output: data/processed/oa_features.parquet, one row per London OA with
  - ID columns (OA21CD, LSOA21CD, LAD22CD, LAD22NM),
  - "<group>_base": each table's own denominator (kept for index scores in step 6),
  - percentage features (each group sums to 100), and
  - pop_density_per_km2 (a rate, passed through unchanged).
OAs that cannot be built are dropped and logged with a reason in outputs/tables/.

Run with:  python -m tessera.wrangle
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tessera import config, quality

MEASURE_SUFFIX = "; measures: Value"
ID_COLUMNS = ["OA21CD", "LSOA21CD", "LAD22CD", "LAD22NM"]
NOMIS_DROP = ["date", "geography"]


def clean_label(column: str) -> str:
    """'Tenure of household: Owned: Owns outright; measures: Value' -> 'Owned: Owns outright'."""
    label = column.removesuffix(MEASURE_SUFFIX)
    _, sep, rest = label.partition(": ")
    return rest if sep else label


def read_oa_table(path: Path, oa_codes: pd.Index | None = None) -> pd.DataFrame:
    """Read a Nomis OA CSV, index it by OA code and clean its column labels."""
    df = pd.read_csv(path).drop(columns=NOMIS_DROP).rename(columns={"geography code": "OA21CD"})
    if oa_codes is not None:
        df = df[df["OA21CD"].isin(oa_codes)]
    df = df.set_index("OA21CD")
    df.columns = [clean_label(c) for c in df.columns]
    if df.columns.duplicated().any():
        raise ValueError(f"{path.name}: duplicate labels after cleaning")
    return df


def table_to_percentages(counts: pd.DataFrame, spec: config.TableSpec) -> pd.DataFrame:
    """Collapse categories into features as % of the table's own total."""
    needed = [spec.denominator] + [label for labels in spec.features.values() for label in labels]
    missing = [label for label in needed if label not in counts.columns]
    if missing:
        raise KeyError(f"{spec.table}: labels not found: {missing}")
    base = counts[spec.denominator]
    out = pd.DataFrame({f"{spec.group}_base": base}, index=counts.index)
    for feature, labels in spec.features.items():
        # A zero base gives NaN, never inf: such OAs are dropped and logged later.
        out[feature] = 100 * counts[labels].sum(axis=1) / base.where(base > 0)
    return out


def density_feature(table: pd.DataFrame) -> pd.DataFrame:
    if config.DENSITY_LABEL not in table.columns:
        raise KeyError(f"{config.DENSITY_TABLE}: label not found: {config.DENSITY_LABEL}")
    return table[[config.DENSITY_LABEL]].rename(columns={config.DENSITY_LABEL: config.DENSITY_FEATURE})


def build_features(
    lookup: pd.DataFrame, tables: dict[str, pd.DataFrame]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join all tables onto the London lookup. Returns (features, dropped OAs with reasons)."""
    features = lookup[ID_COLUMNS].set_index("OA21CD")
    reasons: dict[str, list[str]] = {}

    parts = [table_to_percentages(tables[spec.table], spec) for spec in config.TABLE_SPECS]
    parts.append(density_feature(tables[config.DENSITY_TABLE]))
    names = [spec.table for spec in config.TABLE_SPECS] + [config.DENSITY_TABLE]
    for name, part in zip(names, parts):
        for oa in features.index.difference(part.index):
            reasons.setdefault(oa, []).append(f"missing from {name}")
        features = features.join(part, how="left")

    value_cols = [c for c in features.columns if c not in ID_COLUMNS]
    for oa, row in features.loc[features[value_cols].isna().any(axis=1), value_cols].iterrows():
        if oa not in reasons:
            reasons[oa] = [f"zero denominator or null in {', '.join(row.index[row.isna()])}"]

    dropped = pd.DataFrame(
        [(oa, "; ".join(r)) for oa, r in sorted(reasons.items())], columns=["OA21CD", "reason"]
    )
    features = features.drop(index=list(reasons)).reset_index()
    return features, dropped


def load_tables(raw_dir: Path, oa_codes: pd.Index) -> dict[str, pd.DataFrame]:
    tables = [spec.table for spec in config.TABLE_SPECS] + [config.DENSITY_TABLE]
    return {t: read_oa_table(raw_dir / f"census2021-{t}-oa.csv", oa_codes) for t in tables}


def summarise(features: pd.DataFrame) -> pd.DataFrame:
    numeric = features.drop(columns=ID_COLUMNS)
    return numeric.describe(percentiles=[0.01, 0.5, 0.99]).T


def main() -> None:
    lookup = pd.read_csv(config.OA_LOOKUP_LONDON, dtype=str)
    tables = load_tables(config.RAW_DIR, pd.Index(lookup["OA21CD"]))
    features, dropped = build_features(lookup, tables)

    expected = config.EXPECTED_LONDON_OAS - len(dropped)
    failures = quality.validate_features(features, expected_rows=expected)
    if len(lookup) != config.EXPECTED_LONDON_OAS:
        failures.append(f"London lookup has {len(lookup):,} OAs, expected {config.EXPECTED_LONDON_OAS:,}")
    quality.assert_valid(failures)

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    features.to_parquet(config.OA_FEATURES, index=False)
    dropped.to_csv(config.DROPPED_OAS, index=False)
    summarise(features).to_csv(config.TABLES_DIR / "oa_features_summary.csv")

    deviation = quality.percent_group_deviation(features, quality.percent_groups())
    n_pct = sum(len(s.features) for s in config.TABLE_SPECS)
    print(f"London OAs in lookup:   {len(lookup):,}")
    print(f"OAs dropped:            {len(dropped):,}  (log: {config.DROPPED_OAS.name})")
    for reason, n in dropped["reason"].value_counts().items():
        print(f"    {n:,}  {reason}")
    print(f"OAs written:            {len(features):,}  -> {config.OA_FEATURES.name}")
    print(f"Features:               {n_pct} percentages + 1 density = {n_pct + 1}")
    print("Max |group sum - 100|:  " + ", ".join(f"{g} {v:.2e}" for g, v in deviation.items()))
    print("Quality checks:         all passed")


if __name__ == "__main__":
    main()
