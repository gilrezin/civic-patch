# civic-patch

Website for reimagining city planning parcel-by-parcel using patchwork, collaborative generative AI methods.

Residents draw an area on a full-screen satellite map and describe how it should be improved. The backend crops that patch of imagery, asks Google Gemini's image-editing model (Nano Banana) to apply the change, and overlays the result seamlessly on the map. Everyone can see every edit, vote on it, comment, and refine it further.

## Layout

```
backend/   FastAPI + SQLite + Pillow + google-genai (Python 3.12+)
frontend/  React + Vite + TypeScript + MapLibre GL JS
references/  proposal and UI mockups
```

## Prerequisites

- Python 3.12 or newer (developed on 3.14)
- Node.js 20 or newer (developed on 24)
- A Gemini API key: https://aistudio.google.com/apikey

## Quick start (Windows)

After the one-time setup below (backend venv, `npm install`, `backend/.env`), double-click `dev.bat` or run it from a terminal. It starts both servers in their own windows, opens the site in your default browser, and keeps the launcher window open. Closing the launcher window (or pressing Enter or Ctrl+C in it) stops both servers. Pass `-NoBrowser` to skip opening the browser.

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item example.env .env        # then edit .env and set GEMINI_API_KEY and JWT_SECRET
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000 --timeout-keep-alive 120
```

On macOS/Linux use `source .venv/bin/activate` and `cp example.env .env` instead.

Environment variables (see `backend/example.env`):

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | (required) | Google Gemini API key |
| `GEMINI_IMAGE_MODEL` | `gemini-2.5-flash-image` | Image editing model id |
| `GOOGLE_STREET_VIEW_API_KEY` | (optional) | Google Maps Platform key with the Street View Static API enabled; powers the **View** button |
| `GEMINI_STREETVIEW_MODEL` | `GEMINI_IMAGE_MODEL` | Model that re-renders the street-level panorama (`gemini-3-pro-image-preview` follows the references best) |
| `STREETVIEW_MAX_RADIUS_M` / `STREETVIEW_FACE_PX` / `STREETVIEW_PANO_WIDTH` | `400` / `640` / `2048` | Search radius for a panorama, per-face download size, stitched panorama width |
| `EDITOR` | `gemini` | `fake` runs without any API calls (tints the crop) for offline development |
| `REGION_HINT` | `mask` | `mask` sends the polygon mask as a second image; `text` describes the region in words |
| `JWT_SECRET` | insecure default | Secret for signing login tokens; set a long random string |
| `DATA_DIR` | `./data` | Where the SQLite database and generated images live |
| `PROMPT_HINTS_FILE` | `prompt_hints.json` | Keyword to extra-instruction mapping sent to Gemini (see below) |
| `PLANS_DIR` | `../references` | Folder of per-municipality comprehensive plans used to generate city-specific hints |
| `GEMINI_TEXT_MODEL` / `GEMINI_EMBED_MODEL` | `gemini-2.5-flash` / `gemini-embedding-001` | Models used to generate plan hints |
| `OVERPASS_URLS` / `OVERPASS_TIMEOUT_S` | fr, mail.ru, de, kumi, coffee / `15` | Overpass mirrors for smart select, tried in order |
| `MAX_BBOX_KM2` / `MIN_POLY_M2` | `1.0` / `20` | Selection size guardrails |

### Comprehensive-plan guidance (per municipality)

Drop a municipality's comprehensive plan into a folder named after it under `PLANS_DIR` (default `references/`), for example `references/Philadelphia-PA/Phila2035 Summary_March 2012.pdf`. The folder name is the municipality slug: the city name and the state or region code as Nominatim reports them, joined with hyphens.

When a signed-in user opens the suggestion box over an area, the backend reverse-geocodes the selection, and if that municipality has a plan folder but no generated hints yet, it starts a one-off background job: the documents are extracted (PDF, TXT or MD), chunked, embedded with `GEMINI_EMBED_MODEL`, the best chunks for fourteen planning themes are retrieved, and `GEMINI_TEXT_MODEL` writes a keyword-to-guidance JSON in the same format as `prompt_hints.json`. The result is saved to `DATA_DIR/plan_hints/<Municipality>.json` and is used instead of the default file for every edit and refinement in that municipality. This is invisible to users; the backend log records when generation starts, which source each edit used, and any failures. A generation that is still running when the user submits is awaited for up to a minute. Municipalities without a plan folder fall back to `prompt_hints.json`. Delete the generated file to regenerate it; the chunk index is cached under `DATA_DIR/plan_index/` and reused unless the documents change.

### Prompt hints

`backend/prompt_hints.json` lets you steer Gemini without touching code. Each key is a keyword or phrase; when it appears in a resident's prompt (case-insensitive, whole word, simple plurals allowed, so `bus` matches "buses" and `bike lane` matches "bike lanes"), the value is appended to the model prompt as design guidance. Values may be a string or a list of strings; keys starting with `_` are ignored. The file is re-read whenever it changes, so edits take effect on the next generation without a restart. Example:

```json
{
  "bus": "The bus lanes occupy the outermost lanes of the street unless otherwise specified.",
  "tree": ["Plant street trees in a regular row along the kerb.", "Match shadow direction to the photo."]
}
```
| `GENERATIONS_PER_10_MIN` | `5` | Per-user generation limit |

Run the tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -m "not live"   # unit + API tests: fake editor, stubbed tiles, no network
.\.venv\Scripts\python.exe -m pytest -m live         # one real Gemini call on a Market Street segment
```

The live test stitches real Esri tiles for a stretch of Market Street in Philadelphia, asks Gemini to "add bus lanes", and asserts the returned image is the same size as the crop and that the road pixels inside the polygon actually changed. It skips itself when `backend/.env` has no `GEMINI_API_KEY`, costs one image generation per run, and writes its inputs and outputs to `backend/tests/output/` for inspection.

Alignment check (stitches a real crop and writes an identity overlay you can inspect):

```powershell
.\.venv\Scripts\python.exe -m app.tools.crop_demo out_dir
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` and `/images` to the backend at `http://127.0.0.1:8000` (override with the `VITE_API_TARGET` environment variable, for example `http://127.0.0.1:8001`).

If the site suddenly reports "Not Found" or "Method Not Allowed" for routes that exist, an old backend process is still answering on port 8000. On Windows, stopping `uvicorn --reload` by closing its window or killing the parent can leave the worker alive; find it with `netstat -ano | findstr :8000` and end that PID (or its process tree) before starting the backend again.

For a production build: `npm run build` (output in `frontend/dist/`).

## Using the site

The header shows the city and neighbourhood at the centre of the map and updates as you pan. Click it for a dropdown with the municipality's comprehensive plan (click to download the PDF when one is on file) and a search box for jumping to any place, address or city.

1. Create an account (email + password; your display name is public).
2. Pick an area in one of two ways:
   - **Polygon** (toolbar or `D`): click corners on the map to outline an area. Click the first point, double-click, or press Enter to finish. Backspace undoes a corner, Esc cancels.
   - **Highlighter / quick select** (toolbar or `H`): hold the mouse over a surface and the orange selection grows to neighbouring pixels of similar colour, like Photoshop's Quick Selection. Dragging extends it along the surface. The brush has two concentric radii, both set by the slider: an outer colour-matching reach (up to 50 m at maximum, a constant in the code) and an inner disc half that size that selects every pixel regardless of colour, so small gaps under the cursor fill in. Press Enter (or **Done highlighting**) to finish. Backspace removes the last stroke, Esc cancels.
   - **Smart select** (toolbar or `S`): click a building, parking lot or park to select exactly that object. Click any open ground and the selection grows outward until it meets the surrounding roads, so one click selects a whole block or lot. Roads themselves cannot be selected; they act as boundaries. The search for bounding roads stops at a fixed distance (220 m, a constant in the code), and a block that reaches that limit is cut off there. Drag across several objects to collect them all; click a selected object again to remove it. Works at zoom 17 and closer. Press Enter (or **Done selecting**) to finish, Backspace to undo, Esc to cancel.
3. Type how the area should change and press Enter. Generation takes roughly 10 to 40 seconds; a dashed outline and spinner mark the area meanwhile.
4. Hover any edited area to see its outline; click it or its pin to open the post: votes, the prompt, edit history, **Refine proposal**, **View original**, comments and a share link.
   - **View** (next to the edit history) opens the proposal from street level. The first time, a signed-in user clicks **Generate street view**; the server finds the nearest Street View panorama, stitches a full 360°, and asks Gemini to apply the same change to it. The result is a photo sphere you can drag around, zoom and view full screen, with a **Before / After** switch to compare with the real street. It is generated once per version of the proposal and shared with everyone; after a refinement the pop-up offers to regenerate.
5. Other users' edits, votes and comments appear automatically within about 15 seconds.
6. **My Edits** (header) lists everything you generated: your own suggestions and refinements you made to other people's, each labelled with its neighbourhood and city. Click an entry to jump to it.
7. The **bookmark** icon on a post saves it to your private **Saved** list in the header.
8. The **trash** icon appears on your own suggestions. Deleting asks for confirmation, then removes the suggestion, its refinements, votes and comments from the map for everyone.

Place names come from OpenStreetMap's Nominatim reverse geocoder (one request per edit, rate-limited to the service's one-per-second policy). Edits created before this feature are labelled in the background when the backend starts.

### How smart select finds objects

Smart select does not segment the imagery; it looks up what OpenStreetMap has mapped at the point. The backend fetches buildings, parking lots, green spaces and drivable roads from the Overpass API in fixed 0.01° cells (about 1 km). Cells are cached in memory and in SQLite for 24 hours, so they survive restarts. All Overpass queries pass through a gate of two at a time; a 429 or 503 is retried on the same mirror after a short pause, and only connection failures or timeouts move on to the next mirror in `OVERPASS_URLS` (the French mirror was by far the fastest from the US east coast when tested). The browser loads only the cell under the cursor, plus a neighbour when the cursor is within block-search reach of its edge, and the backend warms the 3×3 cells around a signed-in user's start location in the background. Roads are split into segments at intersections, defined as nodes shared by two or more drivable roads; crosswalks and footpaths do not split a road, and a road that merely continues under the same name across an OSM way boundary stays one segment. Road width comes from the OSM `width` tag, then `lanes`, then a per-class table. In the browser, a click picks the smallest mapped area containing the point (so a building wins over the campus around it). A click on a road is refused. A click on open ground finds the block: nearby roads are rasterised at their width into a 1.5 m grid centred on the click, a flood fill spreads from the click until it meets road cells, and the filled region's outline (simplified) becomes the selection. The grid extends `MAX_BLOCK_SEARCH_M` (220 m) in every direction as a performance failsafe; a fill that reaches the grid edge is clipped there and labelled as cut off. The selection is sent as polygons, and the mask is their union. Outlines are only as good as OSM coverage and usually sit within a metre or two of the Esri imagery; use the highlighter where precision matters or nothing is mapped.

### How quick select picks pixels

The browser fetches the same Esri tiles the map shows, at an integer zoom between 16 and 19 nearest the current view, blurs them lightly and converts them to CIELAB. The slider sets a colour-match radius (`MAX_SPREAD_M`, 50 m, scaled by slider position) and a solid radius half as large. Every pixel in the solid disc is selected outright; a small core of it defines the seed colour, whose mean and spread set a tolerance (base 10 ΔE plus 1.5× the spread, clamped to 8–28). A 4-connected flood fill then accepts neighbours within that tolerance whose lightness gradient is below an edge limit, so it stops at kerbs and roof edges, and never farther than the colour radius from the cursor position that grew them. Strokes union into one pixel mask. On finish the mask's bounding rectangle is sent as a PNG with its tile zoom and origin; the backend resamples it into the crop so Gemini only changes selected pixels, and traces its outline (with holes) for the hover highlight.

## How the imagery pipeline works

- The polygon's bounding box is expanded by a 15% context margin, snapped to a Gemini-supported aspect ratio, and rendered at a zoom level where it is roughly 800 to 1500 px wide.
- Esri World Imagery tiles are fetched and stitched on the server; the crop's bounds are derived from integer tile-pixel edges so the returned image lines up exactly with the basemap.
- Gemini receives the crop, the prompt (with built-environment guardrails), and the polygon mask. The returned image is resized back to the crop size.
- For highlights, the crop covers the bounding box of all strokes and the mask is the strokes themselves (round-capped lines at their ground width), so one Gemini call handles any number of separate marks and only the highlighted pixels are shown.
- A feathered alpha mask limits the overlay to the polygon interior. The map draws it as a raster image source above the basemap, so the original imagery inside the polygon is hidden.
- Refinements send the previous unmasked result back to Gemini with the new instruction, creating a new version in the edit's history.

### How the street view works

Google's Street View Static API only returns single flat views (at most 640×640 px, 120° field of view), never a whole sphere. For the **View** button the backend therefore looks up the nearest outdoor panorama to the edit's centroid (free metadata call, searching outward to `STREETVIEW_MAX_RADIUS_M`), downloads six 90° cube faces of it (four around the horizon, one up, one down; six billable requests, roughly four cents), and reprojects them with numpy into a 2048×1024 equirectangular image whose centre column faces the edit, so the viewer opens looking at the site and the wrap seam sits behind you. Gemini then receives that panorama together with the original satellite crop and the edited version as before/after references, and is asked to render the same change from eye level without altering anything else. Gemini has no 2:1 output ratio, so the panorama is padded to 16:9 with repeated zenith and nadir rows, edited, resized back and cropped. The stitched original and the edited panorama are saved beside the edit's other images (`sv<version>_original.png`, `sv<version>_edited.png`) and served by the pop-up through [Photo Sphere Viewer](https://photo-sphere-viewer.js.org/), which is loaded on demand so the main bundle stays small. A `live` test (`tests/test_live_streetview.py`) stitches a real Market Street panorama into `backend/tests/output/` for inspection.

## Attribution and terms

Basemap imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community. Place names and smart-select outlines © OpenStreetMap contributors (ODbL), via Nominatim and the Overpass API. This prototype uses Esri's public World Imagery tile service without an API key; production use requires an ArcGIS Location Platform account and must follow Esri's terms of use. Generated patches are AI-modified derivatives for visualization only.

Street-level panoramas: imagery © Google, shown with attribution in the viewer. The Google Maps Platform terms allow caching panorama ids but restrict storing Street View imagery and derivatives; this prototype keeps the stitched and AI-edited panoramas on disk so each one is paid for once, which must be reviewed against the current terms before any public deployment.
