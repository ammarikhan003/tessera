"""Project-wide constants: paths, source URLs and table IDs (all verified, see docs/sources.md)."""

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
INTERIM_DIR: Path = DATA_DIR / "interim"
PROCESSED_DIR: Path = DATA_DIR / "processed"

OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"
FIGURES_DIR: Path = OUTPUTS_DIR / "figures"
TABLES_DIR: Path = OUTPUTS_DIR / "tables"

DOCS_DIR: Path = PROJECT_ROOT / "docs"

# --- Census 2021 topic summaries (Nomis bulk downloads) ---------------------
NOMIS_BULK_URL: str = "https://www.nomisweb.co.uk/output/census/2021/census2021-{table}.zip"

CENSUS_TABLES: dict[str, str] = {
    "ts006": "Population density",
    "ts007a": "Age by five-year age bands",
    "ts003": "Household composition",
    "ts054": "Tenure",
    "ts062": "NS-SeC",
    "ts067": "Highest level of qualification",
    "ts045": "Car or van availability",
}

# Tables whose OA value is already a rate, not a count: never convert to
# percentages in step 2 (TS006 is persons per square kilometre).
RATE_TABLES: frozenset[str] = frozenset({"ts006"})

# --- Geography (ONS Open Geography Portal, static downloads) ----------------
OA_BOUNDARIES_URL: str = (
    "https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/"
    "6beafcfd9b9c4c9993a06b6b199d7e6d/geoPackage?layers=0"
)
OA_LOOKUP_URL: str = (
    "https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/"
    "b9ca90c10aaa4b8d9791e9859a38ca67/csv?layers=0"
)
BNG_EPSG: int = 27700  # British National Grid, metres
LONDON_LAD_PREFIX: str = "E09"  # London boroughs + City of London

# --- Benchmark and validation -----------------------------------------------
LOAC_LOOKUP_URL: str = (
    "https://data.london.gov.uk/download/e6600/"
    "845062f2-c5f0-42b4-92b4-d76c4deeb562/LOAC_lookup.csv"
)
# Supergroup/group names and the variables LOAC was built from (same London Datastore page).
LOAC_DESCRIPTIONS_URL: str = (
    "https://data.london.gov.uk/download/e6600/"
    "ac5e56f4-1617-4ab1-9c0f-1118e7c683f2/LOAC_Cluster_Descriptions.pdf"
)
# IMD 2025 is for profiling/validation only, never a clustering feature.
IMD_URL: str = (
    "https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/"
    "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv"
)

# --- File names --------------------------------------------------------------
OA_BOUNDARIES_RAW: Path = RAW_DIR / "oa_2021_ew_bgc_v2.gpkg"
OA_LOOKUP_RAW: Path = RAW_DIR / "oa21_lsoa21_msoa21_lad22_ew_lu_v3.csv"
LOAC_LOOKUP_RAW: Path = RAW_DIR / "loac_lookup.csv"
LOAC_DESCRIPTIONS_RAW: Path = RAW_DIR / "loac_cluster_descriptions.pdf"
IMD_RAW: Path = RAW_DIR / "imd2025_file7.csv"
MANIFEST_PATH: Path = RAW_DIR / "manifest.json"

OA_LOOKUP_LONDON: Path = INTERIM_DIR / "oa_lookup_london.csv"
OA_BOUNDARIES_LONDON: Path = INTERIM_DIR / "oa_boundaries_london.gpkg"

OA_FEATURES: Path = PROCESSED_DIR / "oa_features.parquet"
DROPPED_OAS: Path = TABLES_DIR / "wrangle_dropped_oas.csv"

# London OAs in the ONS OA21->LAD22 lookup (V3), as printed by download.py on
# 2026-10-06. A guard: if ONS republishes the lookup, wrangling fails loudly.
EXPECTED_LONDON_OAS: int = 26_369
PERCENT_SUM_TOLERANCE: float = 0.01  # percentage points

# --- Feature specification (step 2) -----------------------------------------
# Labels are Nomis column names with the topic prefix and "; measures: Value"
# removed. Each table is divided by ITS OWN total: Census 2021 cells are
# perturbed per table, so totals differ slightly between tables for the same OA.


@dataclass(frozen=True)
class TableSpec:
    table: str
    group: str  # feature prefix; also names the denominator column "<group>_base"
    denominator: str  # label of the table's total column
    features: dict[str, list[str]] = field(default_factory=dict)


# --- Segmentation (step 3) ----------------------------------------------------
RANDOM_SEED: int = 42
K_RANGE: range = range(4, 13)  # k = 4..12 inclusive
KMEANS_N_INIT: int = 50  # independent k-means++ starts per k; best inertia kept
PCA_VARIANCE_THRESHOLD: float = 0.80  # keep the fewest components reaching this
CORRELATION_FLAG: float = 0.80  # report feature pairs with |r| at or above this
LOG_DENSITY_FEATURE: str = "log10_pop_density"

PCA_VARIANCE_TABLE: Path = TABLES_DIR / "pca_explained_variance.csv"
HIGH_CORRELATIONS_TABLE: Path = TABLES_DIR / "feature_correlations_high.csv"
KMEANS_SWEEP_TABLE: Path = TABLES_DIR / "kmeans_sweep.csv"
KMEANS_SWEEP_LABELS: Path = INTERIM_DIR / "kmeans_sweep_labels.parquet"

# k shortlist stability check (step 3b)
K_SHORTLIST: tuple[int, ...] = (7, 8)
STABILITY_SEEDS: tuple[int, ...] = tuple(range(10))
SUBSAMPLE_FRACTION: float = 0.80  # share of OAs refit in each subsample run
K_STABILITY_TABLE: Path = TABLES_DIR / "k_stability.csv"
SMALLEST_CLUSTER_PROFILE_TABLE: Path = TABLES_DIR / "smallest_cluster_profile.csv"

# Final segmentation (step 3c)
FINAL_K: int = 8  # chosen in step 3b: see k_stability.csv
OA_SEGMENTS: Path = PROCESSED_DIR / "oa_segments.parquet"
SEGMENT_SIZES_TABLE: Path = TABLES_DIR / "segment_sizes.csv"
SEGMENT_PROFILE_TABLE: Path = TABLES_DIR / "segment_profiles.csv"
PROFILE_TOP_N: int = 8  # most distinctive features per segment in the small-multiples chart
HEATMAP_Z_CLIP: float = 3.0  # colour scale limit for standardised gaps
# Approved 2026-10-07; each is grounded in segment_profiles.csv (see step 3c/5 notes).
SEGMENT_NAMES: dict[int, str] = {
    1: "Extended-Family Working Households",
    2: "Established Suburban Homeowners",
    3: "Social-Rented Family Neighbourhoods",
    4: "Mixed-Tenure Urban Singles",
    5: "Professional Family Homeowners",
    6: "Young Professional Renters",
    7: "Older Social Renters Living Alone",
    8: "Student Communities",
}

# Maps and Tableau export (step 5)
ANALYSIS_CRS: int = 27700  # British National Grid, metres
EXPORT_CRS: int = 4326  # WGS84 lon/lat, required by GeoJSON (RFC 7946)
HOLE_FLAG_M2: float = 10.0  # borough interior rings below this are reported, then filled as slivers
COVERAGE_SNAP_M: float = 0.01  # snap distance when repairing mismatched shared OA edges
# Coverage simplification on top of the ONS 20 m generalisation. Measured 2026-10-07:
# 20 m removes only 0.6% of vertices but changes some small OAs' area by ~50%.
SIMPLIFY_TOLERANCES_M: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0)
MAX_AREA_CHANGE_PCT: float = 1.0  # use the largest tolerance that changes no OA's area by more than this
GEOJSON_TARGET_MB: float = 10.0  # reported against, not enforced
GEOJSON_DECIMALS: int = 5  # ~0.7 m (lon) x 1.1 m (lat) in London, below the 20 m source generalisation
OA_BOUNDARIES_GEOJSON: Path = PROCESSED_DIR / "oa_boundaries.geojson"  # geometry + OA21CD
BOROUGHS_GEOJSON: Path = PROCESSED_DIR / "boroughs.geojson"
BOROUGH_HOLES_TABLE: Path = TABLES_DIR / "borough_interior_rings.csv"
SIMPLIFY_SWEEP_TABLE: Path = TABLES_DIR / "simplify_sweep.csv"
MAP_ATTRIBUTION: str = (
    "Source: Office for National Statistics licensed under the Open Government Licence v.3.0. "
    "Contains OS data © Crown copyright and database right 2023. Census 2021 OAs; k-means segmentation."
)
GROUP_LABELS: dict[str, str] = {
    "age": "Age",
    "hh": "Household",
    "tenure": "Tenure",
    "nssec": "NS-SeC",
    "qual": "Qualification",
    "cars": "Cars/vans",
}

DENSITY_TABLE: str = "ts006"
DENSITY_LABEL: str = "Persons per square kilometre"
DENSITY_FEATURE: str = "pop_density_per_km2"

TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        table="ts007a",
        group="age",
        denominator="Total",  # all usual residents
        features={
            "age_0_4": ["Aged 4 years and under"],
            "age_5_14": ["Aged 5 to 9 years", "Aged 10 to 14 years"],
            "age_15_24": ["Aged 15 to 19 years", "Aged 20 to 24 years"],
            "age_25_34": ["Aged 25 to 29 years", "Aged 30 to 34 years"],
            "age_35_44": ["Aged 35 to 39 years", "Aged 40 to 44 years"],
            "age_45_64": [
                "Aged 45 to 49 years",
                "Aged 50 to 54 years",
                "Aged 55 to 59 years",
                "Aged 60 to 64 years",
            ],
            "age_65_plus": [
                "Aged 65 to 69 years",
                "Aged 70 to 74 years",
                "Aged 75 to 79 years",
                "Aged 80 to 84 years",
                "Aged 85 years and over",
            ],
        },
    ),
    TableSpec(
        table="ts003",
        group="hh",
        denominator="Total",  # all households
        features={
            "hh_one_person_66_plus": ["One person household: Aged 66 years and over"],
            "hh_one_person_under_66": ["One person household: Other"],
            "hh_family_all_66_plus": ["Single family household: All aged 66 years and over"],
            "hh_couple_no_children": [
                "Single family household: Married or civil partnership couple: No children",
                "Single family household: Cohabiting couple family: No children",
            ],
            "hh_couple_dependent_children": [
                "Single family household: Married or civil partnership couple: Dependent children",
                "Single family household: Cohabiting couple family: With dependent children",
            ],
            "hh_couple_nondependent_children": [
                "Single family household: Married or civil partnership couple: All children non-dependent",
                "Single family household: Cohabiting couple family: All children non-dependent",
            ],
            "hh_lone_parent_dependent_children": [
                "Single family household: Lone parent family: With dependent children"
            ],
            "hh_lone_parent_nondependent_children": [
                "Single family household: Lone parent family: All children non-dependent"
            ],
            "hh_other_dependent_children": ["Other household types: With dependent children"],
            "hh_other_no_dependent_children": [
                "Single family household: Other single family household: Other family composition",
                "Other household types: Other, including all full-time students and all aged 66 years and over",
            ],
        },
    ),
    TableSpec(
        table="ts054",
        group="tenure",
        denominator="Total: All households",
        features={
            "tenure_owned_outright": ["Owned: Owns outright"],
            "tenure_owned_mortgage": ["Owned: Owns with a mortgage or loan"],
            "tenure_shared_ownership": ["Shared ownership: Shared ownership"],
            "tenure_social_rented": [
                "Social rented: Rents from council or Local Authority",
                "Social rented: Other social rented",
            ],
            "tenure_private_rented_or_rent_free": [
                "Private rented: Private landlord or letting agency",
                "Private rented: Other private rented",
                "Lives rent free",
            ],
        },
    ),
    TableSpec(
        table="ts062",
        group="nssec",
        denominator="Total: All usual residents aged 16 years and over",
        features={
            "nssec_higher_managerial_prof": [
                "L1, L2 and L3 Higher managerial, administrative and professional occupations"
            ],
            "nssec_lower_managerial_prof": [
                "L4, L5 and L6 Lower managerial, administrative and professional occupations"
            ],
            "nssec_intermediate": ["L7 Intermediate occupations"],
            "nssec_small_employers_own_account": ["L8 and L9 Small employers and own account workers"],
            "nssec_lower_supervisory_technical": ["L10 and L11 Lower supervisory and technical occupations"],
            "nssec_semi_routine_routine": ["L12 Semi-routine occupations", "L13 Routine occupations"],
            "nssec_never_worked_long_term_unemployed": [
                "L14.1 and L14.2 Never worked and long-term unemployed"
            ],
            "nssec_full_time_students": ["L15 Full-time students"],
        },
    ),
    TableSpec(
        table="ts067",
        group="qual",
        denominator="Total: All usual residents aged 16 years and over",
        features={
            "qual_none": ["No qualifications"],
            "qual_level_1_2": ["Level 1 and entry level qualifications", "Level 2 qualifications"],
            "qual_apprenticeship": ["Apprenticeship"],
            "qual_level_3": ["Level 3 qualifications"],
            "qual_level_4_plus": ["Level 4 qualifications and above"],
            "qual_other": ["Other qualifications"],
        },
    ),
    TableSpec(
        table="ts045",
        group="cars",
        denominator="Total: All households",
        features={
            "cars_none": ["No cars or vans in household"],
            "cars_one": ["1 car or van in household"],
            "cars_two_plus": ["2 cars or vans in household", "3 or more cars or vans in household"],
        },
    ),
)


def census_zip_path(table: str) -> Path:
    return RAW_DIR / f"census2021-{table}.zip"


def census_oa_csv_path(table: str) -> Path:
    return RAW_DIR / f"census2021-{table}-oa.csv"


# --- Index scores: hypothetical mid-price gym chain (step 6) -------------------
# Target customer = residents aged 25-44 x share of 16+ residents in NS-SeC L1-L6
# (managerial/professional), assuming age and NS-SeC are independent within an OA.
# Evidence: Sport England Active Lives Adult Nov 22-23 (see docs/sources.md).
TARGET_AGE_FEATURES: tuple[str, ...] = ("age_25_34", "age_35_44")
TARGET_NSSEC_FEATURES: tuple[str, ...] = ("nssec_higher_managerial_prof", "nssec_lower_managerial_prof")
SMALL_BASE_RESIDENTS: int = 20_000  # flag geographies too small for a stable index (City of London)
INDEX_CHART_N: int = 10  # top and bottom boroughs shown
GYM_INDEX_SEGMENTS_TABLE: Path = TABLES_DIR / "gym_index_segments.csv"
GYM_INDEX_BOROUGHS_TABLE: Path = TABLES_DIR / "gym_index_boroughs.csv"

# --- Tableau inputs (step 7) -----------------------------------------------------
TABLEAU_DIR: Path = PROCESSED_DIR / "tableau"
TABLEAU_OA_CSV: Path = TABLEAU_DIR / "oa_segments_features.csv"
TABLEAU_PROFILES_CSV: Path = TABLEAU_DIR / "segment_profiles.csv"
TABLEAU_INDEX_CSV: Path = TABLEAU_DIR / "index_scores.csv"

# --- LOAC benchmark (step 4) -------------------------------------------------------
# Names from LOAC_Cluster_Descriptions.pdf (CDRC, 24/08/23), appendix pp.16-17.
LOAC_SUPERGROUPS: dict[str, str] = {
    "A": "Professional Employment and Family Lifecycles",
    "B": "The Greater London Mix",
    "C": "Suburban Asian Communities",
    "D": "Central Connected Professionals and Managers",
    "E": "Social Rented Sector Families with Children",
    "F": "Young Families and Mainstream Employment",
    "G": "Older Residents in Owner-Occupied Suburbs",
}
LOAC_GROUPS: dict[str, str] = {
    "A1": "Established Homeowners with Children",
    "A2": "Inner London Working Professionals",
    "A3": "European Enclaves",
    "B1": "Social Rented Sector Professional Support Workers",
    "B2": "Skilled Trades and Construction Workers",
    "C1": "Young Asian Family Terraces",
    "C2": "Settled Semi-Detached Asians",
    "D1": "City Support Workers",
    "D2": "Central and City",
    "D3": "Senior Professionals",
    "E1": "Challenged Inner London Communities",
    "E2": "Social Rented Sector Pockets",
    "F1": "Terraced and Semi-Detached Suburbs",
    "F2": "Social Rented Sector and Diverse Origins",
    "G1": "Professional Periphery",
    "G2": "London Fringe",
}
N_PERMUTATIONS: int = 100  # shuffles used to show the spread of chance ARI/AMI
LOAC_BENCHMARK_TABLE: Path = TABLES_DIR / "loac_benchmark.csv"
LOAC_K_SWEEP_TABLE: Path = TABLES_DIR / "loac_k_sweep.csv"
LOAC_NULL_TABLE: Path = TABLES_DIR / "loac_permutation_null.csv"


def loac_crosstab_path(level: str, normalise: str) -> Path:
    """level: 'supergroup' | 'group'; normalise: 'row_pct' | 'col_pct' | 'count'."""
    return TABLES_DIR / f"loac_crosstab_{level}_{normalise}.csv"
