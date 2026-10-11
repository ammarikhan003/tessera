"""GeoPandas maps of segments and the simplified GeoJSON export for Tableau.

All geometry work happens in British National Grid (EPSG:27700, metres); only the
GeoJSON export is reprojected to WGS84, as RFC 7946 requires.

Run with:  python -m tessera.maps
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # file output only; no display needed

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from pyproj.transformer import TransformerGroup

from tessera import config
from tessera.segment import INK, INK_SECONDARY, SERIES, SURFACE, _save, segment_name

BACKGROUND_FILL = "#e4e3df"  # OAs outside the highlighted segment
BOROUGH_LINE = "#52514e"


def load_segment_geoms() -> gpd.GeoDataFrame:
    """OA polygons joined one-to-one to segment labels; fails on any unmatched OA."""
    geoms = gpd.read_file(config.OA_BOUNDARIES_LONDON)[["OA21CD", "LAD22CD", "LAD22NM", "geometry"]]
    segments = pd.read_parquet(config.OA_SEGMENTS)[["OA21CD", "segment_id"]]
    merged = geoms.merge(segments, on="OA21CD", how="outer", validate="one_to_one", indicator=True)
    unmatched = merged["_merge"].ne("both").sum()
    if unmatched:
        raise ValueError(f"{unmatched} OAs present in only one of boundaries / segments")
    if merged.crs.to_epsg() != config.ANALYSIS_CRS:
        raise ValueError(f"Expected EPSG:{config.ANALYSIS_CRS}, got {merged.crs}")
    return merged.drop(columns="_merge")


def coverage_check(geoms: gpd.GeoSeries) -> tuple[bool, int]:
    """Whether polygons form a valid coverage (no overlaps, edges match exactly), plus invalid-edge count."""
    arr = geoms.to_numpy()
    valid = bool(shapely.coverage_is_valid(arr))
    edges = shapely.coverage_invalid_edges(arr)
    return valid, int((~shapely.is_empty(edges)).sum())


def repair_overlaps(geoms: gpd.GeoSeries, snap_m: float = config.COVERAGE_SNAP_M) -> tuple[gpd.GeoSeries, pd.DataFrame]:
    """Make neighbours whose shared edge doesn't match exactly into a valid coverage.

    For each overlapping pair (i, j), j loses the overlap, then i is snapped to j so both
    carry the same vertices where their edges cross. Returns the repaired series and a
    log of each pair with the overlap area removed. Handles mismatches between two OAs
    only (the defect in the source file); callers must re-check coverage validity.
    """
    arr = geoms.to_numpy().copy()
    bad = np.flatnonzero(~shapely.is_empty(shapely.coverage_invalid_edges(arr)))
    tree = shapely.STRtree(arr)
    log = []
    for i in bad:
        for j in tree.query(arr[i], predicate="intersects"):
            overlap = shapely.area(shapely.intersection(arr[i], arr[j])) if j > i else 0.0
            if overlap > 0:
                arr[j] = shapely.difference(arr[j], arr[i])
                arr[i] = shapely.snap(arr[i], arr[j], snap_m)
                log.append({"kept": geoms.index[i], "trimmed": geoms.index[j], "overlap_m2": overlap})
    repaired = gpd.GeoSeries(arr, index=geoms.index, crs=geoms.crs)
    return repaired, pd.DataFrame(log, columns=["kept", "trimmed", "overlap_m2"])


def fill_small_holes(geom: shapely.Geometry, max_area: float) -> shapely.Geometry:
    parts = [
        shapely.Polygon(p.exterior, [r for r in p.interiors if shapely.Polygon(r).area >= max_area])
        for p in shapely.get_parts(geom)
    ]
    return shapely.MultiPolygon(parts) if len(parts) > 1 else parts[0]


def dissolve_boroughs(oas: gpd.GeoDataFrame, fill_below_m2: float = 0.0) -> gpd.GeoDataFrame:
    """Borough polygons as the union of their OAs (OAs nest exactly within LADs).

    fill_below_m2 > 0 removes interior rings smaller than that (source slivers, not real holes).
    """
    boroughs = oas[["LAD22CD", "LAD22NM", "geometry"]].dissolve(by=["LAD22CD", "LAD22NM"]).reset_index()
    if fill_below_m2 > 0:
        boroughs["geometry"] = boroughs.geometry.apply(fill_small_holes, max_area=fill_below_m2)
    return boroughs


def interior_rings(boroughs: gpd.GeoDataFrame) -> pd.DataFrame:
    """One row per hole in each borough polygon, with its area in m²."""
    rows = []
    for code, name, geom in boroughs[["LAD22CD", "LAD22NM", "geometry"]].itertuples(index=False):
        for part in shapely.get_parts(geom):
            for ring in part.interiors:
                rows.append({"LAD22CD": code, "LAD22NM": name, "area_m2": shapely.Polygon(ring).area})
    return pd.DataFrame(rows, columns=["LAD22CD", "LAD22NM", "area_m2"])


def simplify_coverage(geoms: gpd.GeoSeries, tolerance: float) -> gpd.GeoSeries:
    """Simplify shared edges once, so neighbouring OAs stay gap- and overlap-free."""
    return gpd.GeoSeries(shapely.coverage_simplify(geoms.to_numpy(), tolerance), index=geoms.index, crs=geoms.crs)


def write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> float:
    """Reproject to WGS84, write RFC 7946 GeoJSON with rounded coordinates; returns size in MB."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    gdf.to_crs(config.EXPORT_CRS).to_file(
        path, driver="GeoJSON", RFC7946="YES", COORDINATE_PRECISION=config.GEOJSON_DECIMALS
    )
    return path.stat().st_size / 1e6


def simplify_sweep(oas: gpd.GeoDataFrame, tolerances: tuple[float, ...]) -> pd.DataFrame:
    """Vertex count, validity, worst OA area change and GeoJSON size of the OA layer at each tolerance."""
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for tol in tolerances:
            simple = oas.assign(geometry=simplify_coverage(oas.geometry, tol)) if tol > 0 else oas
            rows.append(
                {
                    "tolerance_m": tol,
                    "vertices": int(simple.geometry.count_coordinates().sum()),
                    "invalid": int((~simple.geometry.is_valid).sum()),
                    "empty": int(simple.geometry.is_empty.sum()),
                    "coverage_valid": coverage_check(simple.geometry)[0],
                    "max_area_change_pct": float(
                        (100 * (simple.geometry.area / oas.geometry.area - 1)).abs().max()
                    ),
                    "geojson_mb": write_geojson(simple[["OA21CD", "geometry"]], Path(tmp) / f"oa_{tol:g}.geojson"),
                }
            )
    return pd.DataFrame(rows)


def choose_tolerance(sweep: pd.DataFrame, max_area_change_pct: float = config.MAX_AREA_CHANGE_PCT) -> float:
    """Largest tolerance whose output is valid, non-empty, a valid coverage and distorts no OA's area
    by more than max_area_change_pct. Shape fidelity wins over file size."""
    ok = sweep[
        (sweep["invalid"] == 0)
        & (sweep["empty"] == 0)
        & sweep["coverage_valid"].astype(bool)
        & (sweep["max_area_change_pct"] <= max_area_change_pct)
    ]
    if ok.empty:
        raise ValueError(f"No tolerance in {sweep['tolerance_m'].tolist()} passes the checks")
    return float(ok["tolerance_m"].max())


def transformation_description() -> str:
    """The PROJ operation used for 27700 -> 4326 (shows whether the OSTN15 grid is available)."""
    group = TransformerGroup(f"EPSG:{config.ANALYSIS_CRS}", f"EPSG:{config.EXPORT_CRS}", always_xy=True)
    best = group.transformers[0]
    return f"{best.description} (accuracy {best.accuracy} m; best available: {group.best_available})"


def plot_segment_small_multiples(oas: gpd.GeoDataFrame, boroughs: gpd.GeoDataFrame) -> None:
    """One London panel per segment: its OAs in one colour, others grey, borough lines on top.

    Small multiples rather than one 8-colour map: in a choropleth every pair of hues
    can touch, and the 8-slot palette fails the all-pairs colour checks.
    """
    segs = sorted(oas["segment_id"].unique())
    pct = oas["segment_id"].value_counts(normalize=True).mul(100)
    ncols = 4
    nrows = int(np.ceil(len(segs) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.6 * ncols, 3.9 * nrows), facecolor=SURFACE)
    for ax, seg in zip(axes.ravel(), segs):
        colours = np.where(oas["segment_id"] == seg, SERIES, BACKGROUND_FILL)
        # Edge = face colour hides antialiasing seams between neighbouring polygons.
        oas.plot(ax=ax, color=colours, edgecolor=colours, linewidth=0.1)
        boroughs.boundary.plot(ax=ax, color=BOROUGH_LINE, linewidth=0.35)
        ax.set_title(f"{seg}. {segment_name(seg)}\n{pct[seg]:.1f}% of OAs", loc="left", color=INK, fontsize=10)
        ax.set_axis_off()
        ax.set_aspect("equal")
    for ax in axes.ravel()[len(segs):]:
        ax.set_visible(False)
    fig.suptitle("Tessera segments across London's Census 2021 output areas (borough boundaries overlaid)",
                 x=0.01, ha="left", color=INK, fontsize=13)
    fig.text(0.01, 0.005, config.MAP_ATTRIBUTION, color=INK_SECONDARY, fontsize=7.5)
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    _save(fig, "segment_map.png")


def main() -> None:
    oas = load_segment_geoms()
    print(f"OAs joined to segments: {len(oas):,} (CRS EPSG:{oas.crs.to_epsg()})")

    valid, bad_edges = coverage_check(oas.geometry)
    print(f"OA coverage_is_valid (source): {valid} (OAs with invalid edges: {bad_edges})")
    if not valid:
        repaired, log = repair_overlaps(oas.set_index("OA21CD").geometry)
        print("Repaired overlapping neighbours:")
        print(log.to_string(index=False, float_format=lambda v: f"{v:.6f}"))
        oas = oas.assign(geometry=repaired.to_numpy())
        valid, bad_edges = coverage_check(oas.geometry)
        print(f"OA coverage_is_valid (repaired): {valid} (OAs with invalid edges: {bad_edges}); "
              f"all polygons valid: {bool(oas.geometry.is_valid.all())}")

    holes = interior_rings(dissolve_boroughs(oas))
    holes["below_flag"] = holes["area_m2"] < config.HOLE_FLAG_M2
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    holes.to_csv(config.BOROUGH_HOLES_TABLE, index=False)
    print(f"\nInterior rings after dissolve: {len(holes)}; below {config.HOLE_FLAG_M2:g} m²: "
          f"{int(holes['below_flag'].sum())}")
    if len(holes):
        summary = holes.groupby("LAD22NM").agg(rings=("area_m2", "size"), below_flag=("below_flag", "sum"),
                                               min_m2=("area_m2", "min"), max_m2=("area_m2", "max"))
        print(summary.round(4).to_string())
    boroughs = dissolve_boroughs(oas, fill_below_m2=config.HOLE_FLAG_M2)
    parts = shapely.get_num_geometries(boroughs.geometry.to_numpy())
    print(f"Boroughs: {len(boroughs)}; interior rings left after filling: {len(interior_rings(boroughs))}; "
          f"multi-part boroughs: {int((parts > 1).sum())} ({int(parts.sum())} parts in total)")

    plot_segment_small_multiples(oas, boroughs)
    print("\nWrote segment_map.png")

    if not valid:
        raise SystemExit("OA layer is not a valid coverage; refusing to coverage-simplify it")
    sweep = simplify_sweep(oas, config.SIMPLIFY_TOLERANCES_M)
    sweep.to_csv(config.SIMPLIFY_SWEEP_TABLE, index=False)
    print(f"\nSimplification sweep (GeoJSON at {config.GEOJSON_DECIMALS} dp, geometry + OA21CD only):")
    print(sweep.round(3).to_string(index=False))
    tol = choose_tolerance(sweep)

    simple = oas.assign(geometry=simplify_coverage(oas.geometry, tol)) if tol > 0 else oas.copy()
    # Geometry + key only: attributes come from the OA CSV, joined on OA21CD in Tableau.
    oa_mb = write_geojson(simple[["OA21CD", "geometry"]], config.OA_BOUNDARIES_GEOJSON)
    borough_mb = write_geojson(dissolve_boroughs(simple, fill_below_m2=config.HOLE_FLAG_M2),
                               config.BOROUGHS_GEOJSON)
    print(f"\nChosen tolerance: {tol:g} m (largest with max OA area change <= {config.MAX_AREA_CHANGE_PCT:g}%)")
    print(f"Wrote {config.OA_BOUNDARIES_GEOJSON.name} ({oa_mb:.2f} MB; target {config.GEOJSON_TARGET_MB:g} MB"
          f"{' - OVER' if oa_mb > config.GEOJSON_TARGET_MB else ''}) and {config.BOROUGHS_GEOJSON.name} "
          f"({borough_mb:.3f} MB)")
    print(f"27700 -> 4326 via: {transformation_description()}")


if __name__ == "__main__":
    main()
