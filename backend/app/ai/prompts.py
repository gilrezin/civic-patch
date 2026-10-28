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
{region_hint}
Instruction from a resident: "{prompt}"
Return the edited image."""
)

REFINE_TEMPLATE = (
    SYSTEM_PREFIX
    + """
{region_hint}
The attached photo has already been edited. Changes applied so far, in order:
{history}
Apply this further change, keeping the previous changes: "{prompt}"
Return the edited image."""
)

NUDGE = "\nYou must return the edited image as an image, not a description."


def region_hint(mode: str) -> str:
    return REGION_HINT_MASK if mode == "mask" else REGION_HINT_TEXT


def create_prompt(prompt: str, mode: str) -> str:
    return CREATE_TEMPLATE.format(region_hint=region_hint(mode), prompt=prompt)


def refine_prompt(prompt: str, history: list[str], mode: str) -> str:
    recent = history[-5:]
    lines = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(recent)) or "(none)"
    return REFINE_TEMPLATE.format(region_hint=region_hint(mode), history=lines, prompt=prompt)
