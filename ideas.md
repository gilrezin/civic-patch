**- Broad idea -**
Greater interpretability - allow the user to brainstorm as an intermediary during the generative process to encourage thinking through why this development should exist, and why it is needed

This will create better plans and ideas to present to City Council rather than "I think this would be nice"

Ethan's advice:
"What problem do you want to solve?"
- be ambitious in your goal while maintaining laser focus
1. Who am I? 
2. What skills do I know?
3. Who do I know?

Ideas:
- landing page: prompt the user for a target city beforehand, then cache the frontend of a target area with comprehensive plan, wikipedia articles of the neighborhoods, OpenStreetMap urban fabric, ACS US Census target variables, 3d satellite imagery
- 3d satellite imagery of your target area; selectable lots using city/county parcel map dataset (displaying current ownership, authority, local regulations)
- Cities skylines-esque statistic overlay on the target city (use Census data for this) for items such as land values, education, noise pollution, transportation, and more
- AI parcel explainer: search up prior ownership of the given parcel and the recent history of the surrounding area. Present it to the user when a parcel is selected.
- Streetmix.net-esque streets generation: rather than specifying additional items to the street, use a lane-view to visualize how to reconfigure the street, then use that to prompt the image generator to redraw the street upon the satellite imagery
- regulation identifier: determine the generalized regulation in your given city (can be done through AI search bar) on items such as parking minimums, minimum lot sizes, Floor-Area-Ratios, etc.

---

## 30 more ideas from Claude (evidence-based, built on what exists)

Organizing principle: the tool already turns "I think this would be nice" into a picture. These ideas turn the picture into a *case*: what the research says the change will do, who it helps, who it could hurt, and how to say that to Council. Each one names the evidence it leans on and the part of the codebase it plugs into (`hints.py` keyword guidance, `plans.py` retrieval, OSM smart select, the street-view stitch, votes/comments/versions, the municipality slug).

### A. Evidence layers under the map

1. **Vacant-lot "proven treatment" button.** When smart select lands on a parcel in the city's vacant-land dataset (Philadelphia Land Bank / Atlas), offer a one-click proposal that draws exactly the PHS LandCare spec: cleared, graded, grass, a few trees, low wooden post-and-rail fence. Ship the spec as a hint so the image matches the intervention that was actually tested.
   *Evidence:* Branas et al. 2018 (PNAS), citywide cluster-randomized trial in Philadelphia: greened lots cut gun violence ~29% in neighborhoods below the poverty line; South et al. 2018 (JAMA Netw Open): nearby residents' depression fell ~41%.
   *Builds on:* smart select parcel hits, `prompt_hints.json`, the comprehensive-plan hint pipeline.

2. **Abandoned-building remediation mode.** Flag building footprints with open L&I vacancy/violation records; the proposal "secure and reoccupy" draws working doors and windows, cleared lot, lights, and tags the parcel for the doors-and-windows ordinance.
   *Evidence:* Branas et al. 2016 (AJPH) and Kondo et al. 2015: remediated abandoned buildings in Philadelphia associated with ~39% fewer nearby firearm assaults, at trivial cost.
   *Builds on:* OSM building polygons from smart select, municipality open-data lookup keyed by the slug.

3. **Redlining + heat overlay.** Load HOLC "Mapping Inequality" polygons and a surface-temperature raster (Landsat LST or NOAA urban heat-island campaign data). Every proposal gets an "equity context" chip: HOLC grade and heat percentile of the block it touches.
   *Evidence:* Hoffman, Shandas & Pendleton 2020: formerly redlined areas average ~2.6°C hotter than A-graded areas in the same city.
   *Builds on:* the Census stat-overlay idea above; MapLibre raster/fill layers in `layers.ts`.

4. **Canopy before/after.** Measure green-canopy share inside the mask on the original crop and on each generated version (pixel classification or the city's LiDAR canopy layer), and show "canopy 9% → 31%" next to the version. Rank the feed by canopy gain in low-canopy tracts.
   *Evidence:* American Forests Tree Equity Score methodology; Kuo & Sullivan 2001 (vegetation and lower crime/aggression in Chicago public housing); Donovan & Butry 2010 (Portland street trees raise sale prices).
   *Builds on:* `imaging/mask.py` already isolates the region; versions already store full and overlay PNGs.

5. **Highway-adjacent air buffer.** Draw a 300–500 m buffer around motorway/trunk ways (already classified in `geo/streets.py`). Housing, schools, daycare and playground proposals inside the buffer get a warning and mitigation hints (setbacks, vegetative buffers, filtered ventilation).
   *Evidence:* Health Effects Institute 2010 review: traffic-related pollution exposure zone extends 300–500 m from major roads; elevated asthma and cardiovascular risk.
   *Builds on:* `STREET_CLASSES`, Overpass queries, `hints_for`.

6. **Social-vulnerability targeting.** Pull CDC SVI and EPA EJScreen tract scores; show them in the panel and add a "where it helps most" feed sort that boosts proposals in high-vulnerability tracts.
   *Evidence:* standard HIA/EJ practice (CDC SVI, EJScreen, CEJST) for prioritizing capital spending by need.
   *Builds on:* ACS idea above; `list_edits` ordering.

7. **Noise estimate from the street schema.** Estimate road-traffic noise (Lden) from OSM class, lane count and posted speed; when a proposal removes a lane or lowers the design speed, show the predicted dB change against the WHO threshold.
   *Evidence:* WHO 2018 Environmental Noise Guidelines (road traffic below 53 dB Lden); noise scales with speed and volume.
   *Builds on:* the Streetmix-style lane view; OSM `lanes` and `maxspeed` tags.

8. **Stormwater layer.** Overlay FEMA flood zones and the city's combined-sewer-overflow sewersheds. Proposals inside a CSO sewershed get green-stormwater-infrastructure hints (rain gardens, tree trenches, bumpouts with planters) worded in the style of Philadelphia's Green City, Clean Waters program.
   *Evidence:* Philadelphia Water Department GSI outcomes; green infrastructure is the city's adopted CSO strategy, so proposals that include it align with capital funding.
   *Builds on:* plan-hint generation (`plans.py` TOPICS already includes stormwater).

### B. Harm-minimizing pre-checks (the "interpretability intermediary" idea above)

9. **"Who benefits, who bears the cost" critic pass.** Before the image call, run the text model over the resident's prompt plus retrieved plan chunks (reuse `select_context` with the prompt as the query) and produce a three-line impact note: likely beneficiaries, likely harms, who should be consulted. Store it on the version and show it beside the image.
   *Evidence:* Health Impact Assessment practice (WHO/Gothenburg consensus); Arnstein 1969 on participation that informs rather than placates.
   *Builds on:* `plans.py` retrieval, `generate_json`, a new column on `EditVersion`.

10. **Displacement-risk flag with "just green enough" pairing.** Compute an Urban Displacement Project-style typology per tract from ACS (renter share, rent growth, income, recent moves). Amenity-heavy proposals (parks, trails, greenways, plazas) in at-risk tracts get a nudge to pair with anti-displacement measures (community land trust, inclusionary units, tenant protections) and the brief says so.
    *Evidence:* Rigolon & Németh 2020 ("Green gentrification or just green enough?"); Curran & Hamilton 2012; Chapple & Zuk displacement typologies.
    *Builds on:* ACS idea; hint keywords "park", "trail", "greenway".

11. **Induced-demand guard.** If a prompt widens a road or adds general traffic lanes, show the fundamental-law finding and auto-generate a sibling version with the same mask that spends the space on a bus lane or road diet instead. Never block, always compare.
    *Evidence:* Duranton & Turner 2011 (AER): VMT rises roughly one-for-one with lane-miles.
    *Builds on:* versions chain (`parent_version_id`), `refine_prompt`.

12. **Parking-minimum check.** When a prompt adds housing or retail, ask whether to include off-street parking; show the regulation identifier's current minimum, the per-space cost, and default to no surface parking when a transit stop is within 800 m (OSM `public_transport=stop_position`).
    *Evidence:* Shoup, *The High Cost of Free Parking*; Hess & Rehler 2021 on Buffalo's 2017 repeal (developers built less parking where demand was low).
    *Builds on:* regulation identifier idea; Overpass; hints.

13. **Road-diet eligibility.** For 4-lane undivided roads, join state DOT traffic counts (PennDOT open data); when ADT is under ~20k, propose the FHWA configuration (two travel lanes, center turn lane, bike lanes) as a ready-made lane schema.
    *Evidence:* FHWA Proven Safety Countermeasures: road diets cut total crashes 19–47%.
    *Builds on:* lane view, `STREET_CLASSES`, OSM `lanes`.

14. **School-zone safety hints.** If an `amenity=school` is within 400 m of the mask, append Safe Routes to School treatments (raised crossings, curb extensions, leading pedestrian intervals, 20 mph zone markings) and mark the proposal "child safety".
    *Evidence:* DiMaggio & Li 2013: NYC SRTS cut school-travel-hour pedestrian injuries ~44%; Grundy et al. 2009 (BMJ): London 20 mph zones reduced casualties ~42%; FHWA LPI CMF ≈ 0.87.
    *Builds on:* Overpass POI query, hints.

15. **Lighting as a first-class intervention.** Treat "add lighting" as in scope even though a nadir photo barely shows it: generate the daytime image with fixtures, and a street-view night variant to communicate the change. Pull the lighting evidence into the brief.
    *Evidence:* Chalfin et al. 2022 (J Quant Criminol): randomized street-lighting trial in NYC public housing cut outdoor nighttime index crimes ~36%.
    *Builds on:* `SYSTEM_PREFIX` scope rule, street-view ground view.

### C. Better generation guidance

16. **Lane schema validated against real right-of-way.** Extend the Streetmix-style lane view with NACTO defaults (10 ft lanes, 5–7 ft protected bike lanes, bus lane placement) and check the sum against the measured curb-to-curb width (OSM `width`, or road pixel width × metres-per-pixel at the crop zoom). Reject schemas that don't fit before spending a generation.
    *Evidence:* NACTO Urban Street Design Guide; narrower lanes lower operating speeds without raising crash rates.
    *Builds on:* `geo/mercator.py` scale, lane view, hints.

17. **"5 Ds" scorecard per proposal.** Compute Ewing & Cervero's variables for the crop: density, land-use diversity (OSM tags), design (intersection density), destination accessibility, distance to transit. Show how the proposal moves each one and the implied VMT direction.
    *Evidence:* Ewing & Cervero 2010 meta-analysis of travel and the built environment.
    *Builds on:* Overpass cells cached in `OsmCellCache`.

18. **"Legal today" vs "legal if…" side-by-side.** Using the regulation identifier, generate two sibling versions of a housing prompt: what current parking minimums/lot sizes/FAR allow, and what a stated reform would allow. The brief becomes an argument for the reform.
    *Evidence:* Asquith, Mast & Reed 2021 (new buildings lower nearby rents 5–7%); Pennington 2021 (new construction reduces displacement risk nearby); Mast 2021 migration chains.
    *Builds on:* versions chain, regulation identifier.

19. **Transit-frequency awareness.** Ingest GTFS (SEPTA) and compute headways at nearby stops; proposals within 400 m of frequent service get TOD hints (ground-floor retail, no setback, bike parking) and a chip "15-min service within 5 min walk".
    *Evidence:* frequency drives ridership and access more than route count (Walker, *Human Transit*; TCRP reports).
    *Builds on:* municipality slug → GTFS feed registry.

20. **Gehl public-life audit at eye level.** Run the street-view before/after through a checklist (seating, shade, active frontage, edges, crossing distance) and score "stationary activity potential" for the proposal.
    *Evidence:* Gehl public-life studies; Jacobs on active frontages and eyes on the street.
    *Builds on:* six-face street-view stitch and ground-view prompt.

21. **Shade simulation.** Use OSM `building:levels` to cast 3 pm July shadows over the crop and score shade at bus stops, benches and crossings; tree proposals show predicted shade gain.
    *Evidence:* Bloch 2019 *Shade* (LA shade inequity); Hoffman 2020 heat disparities.
    *Builds on:* smart-select building footprints; sun-position math is small.

### D. Participation quality (the research says who shows up is the problem)

22. **Representativeness dashboard.** Optional self-report at sign-up (renter/owner, age band, main travel mode, live within 1 km?). For each proposal, compare voters/commenters to the ACS tract and show "voices missing: renters, under-35".
    *Evidence:* Einstein, Glick & Palmer 2019 *Neighborhood Defenders*: public-meeting participants are older, more likely to own, and far more likely to oppose housing than the neighborhood.
    *Builds on:* `User` model, ACS idea, `_aggregates`.

23. **Deliberative vote.** Before a vote is counted, show a short evidence card (from the evidence library in idea 30) and record pre- and post-card votes. Report both; the delta is itself a finding.
    *Evidence:* Fishkin's deliberative polling shows informed preferences differ systematically from raw ones.
    *Builds on:* `Vote` table (add `informed` flag), `VoteButtons.tsx`.

24. **Votes carry proximity.** Record a coarse distance band (within 1 km, same city, elsewhere) from the browser location; display local vs citywide support separately and let the feed filter on it. Reduces brigading without blocking anyone.
    *Evidence:* same participation-bias literature; councils weigh nearby residents.
    *Builds on:* geolocation already requested; `Vote` schema.

25. **Pairwise comparison instead of up/down.** Let anyone fork an edit (sibling version on the same mask) and show two versions side by side with "which is better for this street?". Fit a Bradley–Terry ranking.
    *Evidence:* MIT Place Pulse (Salesses, Schechtner & Hidalgo 2013) showed pairwise image comparisons give stable streetscape judgments where ratings don't.
    *Builds on:* `parent_version_id`, `VersionHistory.tsx`.

26. **Honest trade-off strip.** Diff OSM features inside the mask against the prompt and the critic note to list what the proposal removes as well as adds: "−18 parking spaces, −1 travel lane, +22 trees, +1 crossing". Shown on every card.
    *Evidence:* HIA and NEPA practice: disclosed trade-offs beat implied ones; also reduces "AI hid the cost" objections.
    *Builds on:* `describeItems` in `osmFeatures.ts`, critic pass.

### E. Advocacy outputs (the path to Council)

27. **Council-ready brief.** One click produces a PDF: before/after satellite, before/after street view, the plan passages it aligns with (page-cited from `plans.py` chunks), the evidence cards, support with representativeness, the council district and the Registered Community Organization (Philadelphia's RCO polygons are open data), and a draft testimony paragraph.
    *Builds on:* everything above; `share()` in `EditPanel.tsx` becomes "Export brief".

28. **Quick-build variant with cost range.** For street proposals, auto-generate a paint-and-planters pilot version (flex posts, epoxy gravel, planters) and attach unit-cost ranges per linear foot and per tree from published capital budgets and NACTO cost sheets.
    *Evidence:* NACTO quick-build guidance; cities adopt pilots that already exist far more readily than concepts.
    *Builds on:* sibling versions, hints.

29. **"Did it happen?" ledger.** Let a proposal be marked "adopted", "piloted" or "built"; periodically re-fetch imagery for its bounds (the satellite-tile refresh already works) and show the real after-photo next to the rendering. Closes the feedback loop and gives the evidence library local effect data.
    *Evidence:* Arnstein's top rungs require feedback to participants; outcome tracking is what distinguishes consultation from placation.
    *Builds on:* `Edit.status` extension, tile fetch in `geo/tiles.py`, a scheduled job.

30. **Evidence library as a hints file.** A versioned `evidence.json` in the same shape as `prompt_hints.json`: intervention keyword → {claim, effect size, citation, study type, where it was tested}. It feeds the critic (9), the deliberative card (23), the trade-off strip (26) and the brief (27), and can be overridden per municipality like `plan_hints`. Keep "RCT in Philadelphia" visibly distinct from "observational, elsewhere" so the tool never overstates.
    *Builds on:* `hints.py` loader (mtime re-read, keyword compile), `plans.py` per-slug layout.

### Suggested first three
If picking a starting point: **30** (evidence library) is cheap and unlocks 9, 23, 26 and 27; **1** (vacant-lot treatment) is the strongest Philadelphia-specific story with an RCT behind it; **22** (representativeness) is the most direct answer to the research on why planning input goes wrong.
