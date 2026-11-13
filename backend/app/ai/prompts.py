"""Prompt templates for satellite-imagery editing."""

from __future__ import annotations

SYSTEM_PREFIX = """You are editing a straight-down (nadir) satellite orthophoto of a city for an urban-planning visualization.
Hard rules:
1. Keep the exact same viewpoint, scale, rotation, framing, lighting, season and photographic style. The output must look like the same satellite photo, top-down, with no perspective or 3D view.
2. Change ONLY what the instruction asks for. Every other building, road, tree, car, shadow and ground surface must stay in the same pixel position and look identical.
3. Do not add text, labels, arrows, borders, legends or watermarks.
4. Only built-environment and land-use changes are allowed (streets, bike and bus lanes, sidewalks, plazas, parks, trees, buildings, housing, parking, transit, water features, public space). If the instruction is not about the physical built environment, do not edit the image; reply with the text OUT_OF_SCOPE and nothing else.
"""

REGION_HINT_MASK = (
    "The second image is a mask of the same photo: white marks the area you may change; "
    "black areas must remain identical."
)
REGION_HINT_TEXT = (
    "The area to change is near the center of the image; the outer ~15% border is context "
    "and must remain identical."
)

CREATE_TEMPLATE = (
    SYSTEM_PREFIX
    + """
{region_hint}{guidance}
Instruction from a resident: "{prompt}"
Return the edited image."""
)

REFINE_TEMPLATE = (
    SYSTEM_PREFIX
    + """
{region_hint}{guidance}
The attached photo has already been edited. Changes applied so far, in order:
{history}
Apply this further change, keeping the previous changes: "{prompt}"
Return the edited image."""
)

NUDGE = "\nYou must return the edited image as an image, not a description."

STREETVIEW_TEMPLATE = """You are editing a 360-degree equirectangular street-level panorama for an urban-planning visualization.
Image 1 is the panorama to edit. Image 2 is a straight-down satellite photo of the same place BEFORE a proposed change. Image 3 is the same satellite photo AFTER the change. The only thing you may change in Image 1 is what differs between Image 2 and Image 3, rendered as it would look from eye level.
The panorama was captured about {distance_m} m from the site{place}. The site lies straight ahead at the horizontal centre of Image 1.
Changes proposed for the site, in order:
{history}
Hard rules:
1. Return the same equirectangular 360 panorama: identical projection, framing, horizon height, field of view and image size. Do not crop, rotate, zoom, re-centre, or turn it into a normal photograph.
2. The left and right edges wrap around to meet each other and must stay continuous.
3. Everything not implied by the satellite before/after pair stays identical: buildings, sky, weather, lighting, season, road markings, parked cars, people and signs.
4. Do not add text, labels, arrows, borders or watermarks.
5. Only built-environment changes are allowed (streets, lanes, sidewalks, plazas, parks, trees, buildings, housing, parking, transit, water features, public space). If the change is not visible from this viewpoint, return the panorama unchanged.
Return the edited panorama as an image."""


def streetview_prompt(history: list[str], place_name: str | None, distance_m: float) -> str:
    lines = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(history[-5:])) or "(none)"
    place = f" in {place_name}" if place_name else ""
    return STREETVIEW_TEMPLATE.format(distance_m=max(1, int(round(distance_m))), place=place, history=lines)


def region_hint(mode: str) -> str:
    return REGION_HINT_MASK if mode == "mask" else REGION_HINT_TEXT


def format_guidance(hints: list[str] | None) -> str:
    """Extra design guidance (from prompt_hints.json) as a numbered block, or empty."""
    if not hints:
        return ""
    lines = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(hints))
    return f"\nDesign guidance from the planning team for this request:\n{lines}"


def create_prompt(prompt: str, mode: str, hints: list[str] | None = None) -> str:
    return CREATE_TEMPLATE.format(region_hint=region_hint(mode), guidance=format_guidance(hints), prompt=prompt)


def refine_prompt(prompt: str, history: list[str], mode: str, hints: list[str] | None = None) -> str:
    recent = history[-5:]
    lines = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(recent)) or "(none)"
    return REFINE_TEMPLATE.format(
        region_hint=region_hint(mode), guidance=format_guidance(hints), history=lines, prompt=prompt
    )
