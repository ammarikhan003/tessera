# Data sources

Every source was verified online on 2026-10-06 before use. Download times,
sizes and SHA-256 hashes come from `data/raw/manifest.json`, written by
`python -m tessera.download`; rerun it to reproduce `data/raw/`.

## Census 2021 topic summaries (Nomis bulk downloads)

Publisher: ONS via Nomis. Index page: <https://www.nomisweb.co.uk/sources/census_2021_bulk>.
Each zip holds one CSV per geography; only `census2021-<id>-oa.csv` is used.
Licence: Open Government Licence v3.0.

| Table ID | Title | URL | Downloaded (UTC) | Notes |
|----------|-------|-----|------------------|-------|
| TS006  | Population density | https://www.nomisweb.co.uk/output/census/2021/census2021-ts006.zip | 2026-10-06T20:08:30 | **Rate** (persons per km²), not a count: do not convert to percentages |
| TS007A | Age by five-year age bands | https://www.nomisweb.co.uk/output/census/2021/census2021-ts007a.zip | 2026-10-06T20:08:37 | |
| TS003  | Household composition | https://www.nomisweb.co.uk/output/census/2021/census2021-ts003.zip | 2026-10-06T20:08:43 | |
| TS054  | Tenure | https://www.nomisweb.co.uk/output/census/2021/census2021-ts054.zip | 2026-10-06T20:08:46 | |
| TS062  | NS-SeC | https://www.nomisweb.co.uk/output/census/2021/census2021-ts062.zip | 2026-10-06T20:08:50 | |
| TS067  | Highest level of qualification | https://www.nomisweb.co.uk/output/census/2021/census2021-ts067.zip | 2026-10-06T20:08:54 | |
| TS045  | Car or van availability | https://www.nomisweb.co.uk/output/census/2021/census2021-ts045.zip | 2026-10-06T20:08:56 | |

## Geography (ONS Open Geography Portal)

Licence: Open Government Licence v3.0 (<https://www.ons.gov.uk/methodology/geography/licences>).
Required attribution: "Source: Office for National Statistics licensed under the
Open Government Licence v.3.0". The boundary file additionally needs
"Contains OS data © Crown copyright and database right [year]".
Neither the licence page nor the boundary item's metadata states the year
(checked 2026-10-08); the item's last version amendment is 14 July 2023, so the
dashboard uses 2023.

| Dataset | ID | URL | Downloaded (UTC) | Notes |
|---------|----|-----|------------------|-------|
| Output Areas (December 2021) Boundaries EW BGC (V2) | item `6beafcfd9b9c4c9993a06b6b199d7e6d` | https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/6beafcfd9b9c4c9993a06b6b199d7e6d/geoPackage?layers=0 | 2026-10-06T20:09:25 | National GeoPackage, EPSG:27700, generalised (20 m) and clipped to coastline. No LAD field, so London is selected via the lookup |
| Output Area (2021) to LSOA to MSOA to LAD (December 2021) Exact Fit Lookup in EW (V3) | item `b9ca90c10aaa4b8d9791e9859a38ca67` | https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/b9ca90c10aaa4b8d9791e9859a38ca67/csv?layers=0 | 2026-10-06T20:09:00 | London = `LAD22CD` starting `E09` |

The hub download links redirect to generated export files; their bytes can
change if ONS regenerates them, which the manifest hash would reveal.

## Benchmark and validation

| Dataset | Publisher | URL | Downloaded (UTC) | Notes |
|---------|-----------|-----|------------------|-------|
| London Output Area Classification (2021), `LOAC_lookup.csv` | GLA (London Datastore, <https://data.london.gov.uk/dataset/london-output-area-classification>) | https://data.london.gov.uk/download/e6600/845062f2-c5f0-42b4-92b4-d76c4deeb562/LOAC_lookup.csv | 2026-10-06T20:09:26 | Columns `OA, G, SG`. OGL v3.0. Group names are in `LOAC_Cluster_Descriptions.pdf` on the same page |
| LOAC Cluster Descriptions, `LOAC_Cluster_Descriptions.pdf` (Consumer Data Research Centre; A. Singleton, P. Longley; dated 24/08/23) | GLA (London Datastore, same page) | https://data.london.gov.uk/download/e6600/ac5e56f4-1617-4ab1-9c0f-1118e7c683f2/LOAC_Cluster_Descriptions.pdf | 2026-10-06T22:50:04 | OGL v3.0. Supergroup/group names taken from the appendix typology table (pp.16-17) into `config.LOAC_SUPERGROUPS` / `LOAC_GROUPS`. The descriptions reference ethnicity, religion, country of birth, language and industry, which Tessera does not use; the PDF does not list LOAC's full input variables |
| English Indices of Deprivation 2025, File 7 (all ranks, scores, deciles, population denominators) | MHCLG (<https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025>) | https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv | 2026-10-06T20:09:28 | LSOA 2021 level; published 30 Oct 2025. **Profiling/validation only, never a clustering feature** |

## Target-customer evidence (step 6)

Used only to justify the gym target definition; no figures from it enter any calculation.

| Document | Publisher | URL | Accessed (UTC) | Figures used |
|----------|-----------|-----|----------------|--------------|
| Active Lives Adult Survey November 2022-23 Report (published April 2024; England, adults 16+) | Sport England (<https://www.sportengland.org/research-and-data/data/active-lives>) | https://activenorfolk.org/app/uploads/2025/04/Active-Lives-Adult-Survey-November-2022-23-Report.pdf (copy hosted by Active Norfolk) | 2026-10-07 | "Active" (150+ min/week) by age, p.9-10: 16-34 70.1%, 35-54 65.6%, 55-74 62.3%, 75+ 42.8%. By NS-SEC (ages 16-74), p.13: NS-SEC 1-2 72.7%, 3-5 62.1%, 6-8 52.6%. These measure overall activity, not gym membership |
