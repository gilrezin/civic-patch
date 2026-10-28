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
| `EDITOR` | `gemini` | `fake` runs without any API calls (tints the crop) for offline development |
| `REGION_HINT` | `mask` | `mask` sends the polygon mask as a second image; `text` describes the region in words |
| `JWT_SECRET` | insecure default | Secret for signing login tokens; set a long random string |
| `DATA_DIR` | `./data` | Where the SQLite database and generated images live |
| `MAX_BBOX_KM2` / `MIN_POLY_M2` | `1.0` / `20` | Selection size guardrails |
| `GENERATIONS_PER_10_MIN` | `5` | Per-user generation limit |

Run the tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

The tests use the fake editor and stubbed tiles, so they need no network or API key.

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

Open http://localhost:5173. The dev server proxies `/api` and `/images` to the backend on port 8000.

For a production build: `npm run build` (output in `frontend/dist/`).

## Using the site

1. Create an account (email + password; your display name is public).
2. Click **Suggest an improvement** (or press `D`), then click corners on the map to outline an area. Click the first point, double-click, or press Enter to finish. Backspace undoes a corner, Esc cancels.
3. Type how the area should change and press Enter. Generation takes roughly 10 to 40 seconds; a dashed outline and spinner mark the area meanwhile.
4. Hover any edited area to see its outline; click it or its pin to open the post: votes, the prompt, edit history, **Refine proposal**, **View original**, comments and a share link.
5. Other users' edits, votes and comments appear automatically within about 15 seconds.

## How the imagery pipeline works

- The polygon's bounding box is expanded by a 15% context margin, snapped to a Gemini-supported aspect ratio, and rendered at a zoom level where it is roughly 800 to 1500 px wide.
- Esri World Imagery tiles are fetched and stitched on the server; the crop's bounds are derived from integer tile-pixel edges so the returned image lines up exactly with the basemap.
- Gemini receives the crop, the prompt (with built-environment guardrails), and the polygon mask. The returned image is resized back to the crop size.
- A feathered alpha mask limits the overlay to the polygon interior. The map draws it as a raster image source above the basemap, so the original imagery inside the polygon is hidden.
- Refinements send the previous unmasked result back to Gemini with the new instruction, creating a new version in the edit's history.

## Attribution and terms

Basemap imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community. This prototype uses Esri's public World Imagery tile service without an API key; production use requires an ArcGIS Location Platform account and must follow Esri's terms of use. Generated patches are AI-modified derivatives for visualization only.
