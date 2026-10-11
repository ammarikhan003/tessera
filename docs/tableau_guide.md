# Building the Tessera dashboard in Tableau Public (first-timer's guide)

You'll build one dashboard with three parts: a **segment map** of London's output
areas, a **segment profile heatmap**, and **gym index scores** for segments and
boroughs. Allow about 2-3 hours the first time.

Menu names below come from Tableau's help pages (checked 2026-10-07). Small wording
differences between versions are normal; the help links at the end show the current wording.

## 0. The input files

Regenerate them any time with `python -m tessera.tableau_export` (after
`segment --final`, `maps` and `index_scores`). Everything is in `data/processed/tableau/`:

| File | One row is... | Use it for |
|------|---------------|------------|
| `oa_boundaries.geojson` | one OA polygon (only field: `OA21CD`) | map shapes |
| `oa_segments_features.csv` | one OA: codes, borough, `segment_id`, `segment_name`, `residents`, `households`, density, 39 % features, `gym_target_est` | everything shown on the map |
| `boroughs.geojson` | one borough outline | optional map overlay |
| `segment_profiles.csv` | one segment x one feature: `segment_pct`, `london_pct`, `index`, `z` + segment sizes | profile heatmap |
| `index_scores.csv` | one segment **or** borough (`level` column): `index`, `target_est`, `pct_of_london_target`, component indices, `small_base` | index charts |

Percentages are stored as 0-100 numbers (e.g. 23.5 means 23.5%), not 0-1.

## 1. Install and sign up

1. Go to <https://public.tableau.com>, create a free account, and download
   **Tableau Desktop Public Edition** (the free desktop app).
2. Install and open it. You'll see the **Connect** pane on the left.

Two facts to keep in mind:
- Anything you **publish** to Tableau Public is visible to everyone. That's fine
  here, because it's all published Census data.
- You can also save workbooks **locally** in the Public Edition, so save often
  while you work (File > Save).

## 2. Data source 1: the map (GeoJSON + OA CSV)

Tableau terms: a *data source* is a set of connected tables. A *relationship*
tells Tableau how two tables match up (here, by OA code) without merging them into one.

1. In **Connect**, under *To a File*, click **Spatial file**, select
   `oa_boundaries.geojson` and click **Open**. The Data Source page opens with the
   file on the canvas.
2. Top left, under **Connections**, click **Add**, choose **Text file**, then
   select `oa_segments_features.csv`.
3. Drag `oa_segments_features.csv` from the left onto the canvas, next to the
   GeoJSON table. When a line (Tableau calls it a "noodle") appears between them,
   drop it.
4. In the relationship panel below the canvas, make sure the pair is
   **OA21CD = OA21CD**. Both fields must have the same data type (text, shown as
   *Abc*). If Tableau reads one as a number, click the type icon above that column
   and change it to **String**.
5. Rename the data source (top of the page) to `OA map`.

**Check:** do this once the map is drawn (section 4, step 3). The status bar at
the bottom left of the window (**Window > Show Status Bar** if it's hidden) should
report **26,369 marks**, and the `segment_name` colour legend should have no
**Null** entry. A Null entry means some OA shapes found no matching CSV row;
go back to step 4. (A field from only one table doesn't test the relationship,
because Tableau queries just that table.)

## 3. Data sources 2 and 3: the two other CSVs

These two files don't need the map, so each becomes its own data source:

1. **Data > New Data Source > Text file**, then pick `segment_profiles.csv`.
   Rename it `Profiles`.
2. **Data > New Data Source > Text file**, then pick `index_scores.csv`.
   Rename it `Index scores`.
   - Check that `geo_id` is a **String** (*Abc*), not a number. Segment IDs are
     1-8 but borough IDs are codes like E09000001, so the column has to be text.

## 4. Sheet "Segment map"

1. Make sure the `OA map` data source is selected (top of the Data pane), then
   rename the sheet tab to `Segment map`.
2. **Double-click `Geometry`.** Tableau draws all 26,369 OAs. It adds Geometry to
   **Detail** on the Marks card, plus generated Latitude/Longitude fields.
3. Drag `segment_name` onto **Color**. A colour legend appears.
4. **Colour, read this first.** With 8 segments, no palette lets every pair of
   colours be told apart everywhere on a map (we tested this in step 5 of the
   project). So don't rely on colour alone:
   - Click the legend's drop-down > **Edit Colors**, and choose eight clearly
     different colours.
   - Step 8 adds click-to-highlight and a segment filter, so viewers can isolate
     one segment at a time. That works regardless of colour vision.
5. Make the boundaries quieter: Marks card **Color > Border > None**. 26,000
   outlines would turn the map grey.
6. **Tooltip:** drag `segment_name`, `LAD22NM`, `residents` and `gym_target_est`
   onto **Tooltip**, then click **Tooltip** to tidy the text.
   - `gym_target_est` is an *estimate*; format it with 0 decimals (right-click >
     **Format**).
7. **Optional borough outlines:**
   - Add `boroughs.geojson` as another **Spatial file** connection in this data
     source.
   - Relate it on borough code: `LAD22CD` in `boroughs.geojson` = `LAD22CD` in
     the CSV.
   - Drag its `Geometry` onto the map and drop it on **Add a Marks Layer**.
   - On that layer set **Color** to no fill (opacity 0%) with a thin dark border.
   - If this is fiddly, skip it. The map works without it.

## 5. Sheet "Segment profiles" (heatmap)

1. New sheet, data source `Profiles`. Rename it `Segment profiles`.
2. Drag `segment_name` to **Columns**.
3. Drag `topic`, then `feature_label`, to **Rows**.
4. Sort the features by Census order: right-click `feature_label` on Rows >
   **Sort** > **Field** > `feature_order` > Ascending, aggregation **Minimum**.
   Do the same for `topic` (otherwise topics sort alphabetically: Age, Cars/vans,
   Household...), and sort `segment_name` on Columns by `segment_id`, Minimum.
5. Marks card: change **Automatic** to **Square**.
6. Drag `z` to **Color**. Click the colour legend > **Edit Colors**:
   - choose a **diverging** palette (e.g. *Orange-Blue Diverging*)
   - tick **Use Full Color Range**
   - under **Advanced**, set **Center** to 0, **Start** to -3 and **End** to 3
   - result: grey = typical of London; strong colours = very different
7. Drag `index` to **Label**. Format it as a whole number (right-click >
   **Format** > Numbers > Number (Custom), 0 decimals).
8. Tooltip: add `segment_pct` and `london_pct`, e.g. "Segment 36.7% vs London 18.1%".
9. **Aggregation trap.** The profile file repeats each segment's size on every
   row (39 times), so `SUM(residents)` would be 39x too big. Whenever you use a
   size column (`residents`, `n_oas`, `pct_n_oas`…), right-click it >
   **Measure** > **Minimum** (or **Attribute**). `segment_pct`, `index` and `z`
   are fine: each segment × feature cell holds exactly one row.

## 6. Sheet "Segment index"

1. New sheet, data source `Index scores`. Rename it `Segment index`.
2. Drag `level` to **Filters**, then tick only `segment`.
3. Drag `geo_name` to **Rows** and `index` to **Columns**. Sort descending (the
   sort icon on the toolbar).
4. Add the London line: open the **Analytics** pane (tab next to Data), drag
   **Reference Line** onto the view, choose **Table**, set the value to
   **Constant** = 100 and label it "London = 100".
5. Drag `target_est` to **Label** (format as thousands, e.g. 276.2K) and
   `pct_of_london_target` to **Tooltip**.
   - The index shows **concentration**; the label shows **volume**. Keep both
     visible, because that contrast is the main finding (see step 9).

## 7. Sheet "Borough index"

1. Right-click the `Segment index` tab > **Duplicate**, and rename the copy
   `Borough index`.
2. Change the `level` filter to `borough`.
3. All 33 boroughs fit if you shrink the row height (drag the bottom edge of a
   row). Alternatively, show the top 10 and bottom 10 like
   `outputs/figures/gym_index_boroughs.png`, using a Top N filter on `geo_name`
   by `index`.
4. Flag City of London: drag `small_base` to **Color**, choose a muted colour
   for *True*, and add a caption: "City of London has ~8,600 residents, so its
   index is unstable."

## 8. The dashboard

1. Click the **New Dashboard** icon (bottom bar, next to the new-sheet icon).
2. **Size** (left panel): choose **Fixed size**, e.g. 1400 × 900, so it looks
   the same for every viewer.
3. Drag sheets from the left onto the canvas. A layout that works:
   - the map on the left, about 55% of the width
   - the profile heatmap on the right
   - the two index charts underneath, side by side
4. Add a title (**Objects > Text**), plus a text box with:
   - the gym target definition
   - the independence assumption
   - the attribution: "Source: Office for National Statistics licensed under
     the Open Government Licence v.3.0. Contains OS data © Crown copyright and
     database right [year]." Check the year with the boundary dataset page.
5. **Interactivity: click a segment, and everything filters to it.**
   - **Dashboard > Actions > Add Action > Filter**.
   - Source sheet: `Segment map`. Targets: `Segment profiles` and `Segment index`.
     Run action on: **Select**.
   - The sheets use different data sources, so under *Target Filters* choose
     **Selected Fields** and map `segment_name` → `segment_name` for
     `Segment profiles`, and `segment_name` → `geo_name` for `Segment index`
     (`index_scores.csv` holds segments and boroughs in one `geo_name` column;
     the segment names match exactly).
   - Clearing the selection: **Show all values**.
6. **Highlight** for colour-blind-friendly exploration: **Dashboard > Actions >
   Add Action > Highlight**, source `Segment map`, on **Hover** or **Select**. It
   fades every other segment, so the segment you're looking at stands out
   whatever its colour.
7. Optional: on the map sheet, right-click `segment_name` > **Show Filter**
   (single value, drop-down) to give a "pick a segment" control.

## 9. What the dashboard should show (to check your build)

These figures come from `python -m tessera.index_scores`. If your dashboard
shows different values, there's a join or aggregation problem.
- **Young Professional Renters:** index **255.4**; holds **23.3%** of London's
  estimated target from **9.1%** of residents.
- **Extended-Family Working Households:** index **59.5**, yet **14.1%** of the
  target (~167,000 people), because it's London's largest segment.
- **Wandsworth:** the highest index among sizeable boroughs, **174.5**, and the
  largest volume, about **77,000**.
- **Barking and Dagenham:** the lowest index, **53.9**.

## 10. Save and publish

1. **File > Save** keeps a local copy (do this throughout).
2. **Server > Tableau Public > Save to Tableau Public**, sign in, and give it a
   title. It uploads the data with the workbook and opens the published page in
   your browser.
3. On the published page, add a description and link the GitHub repo. Then put
   the Tableau Public link in the README.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Map is empty or shows a single point | Geometry isn't on Detail, or the file was opened as text | Reconnect with **Spatial file**; double-click `Geometry` |
| Map is grey with no segment colours | Relationship isn't matching | Check that `OA21CD` = `OA21CD`, both String; the 26,369-mark check in step 2 |
| Profile size numbers are 39× too big | `SUM` on a repeated column | Set the measure to **Minimum** or **Attribute** (step 5.9) |
| `geo_id` shows as a number with blanks | Read as a number | Change it to **String** on the Data Source page |
| Filter action does nothing | Field mapping missing between data sources | Actions > edit > **Selected Fields** > `segment_name` → `segment_name` |
| Slow map | 26k polygons take a few seconds to draw | Expected; build the other sheets while it renders, and keep Border at None |

## Help pages used

- Connect to spatial files: <https://help.tableau.com/current/pro/desktop/en-us/maps_shapefiles.htm>
- Relationships: <https://help.tableau.com/current/pro/desktop/en-us/relate_tables.htm>
- Joining spatial files: <https://help.tableau.com/current/pro/desktop/en-us/maps_spatial_join.htm>
- Saving to Tableau Public: <https://help.tableau.com/current/pro/desktop/en-us/publish_workbooks_tableaupublic.htm>
- Local save in Desktop Public Edition: <https://www.tableau.com/blog/local-file-save-tableau-desktop-public-edition>
