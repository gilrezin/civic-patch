"""Keyword-triggered extra instructions for Gemini, loaded from a customisable JSON file.

The file maps keywords/phrases to guidance text. When a resident's prompt contains a key
(case-insensitive whole word or phrase, simple plurals allowed), the guidance is appended
to the model prompt. The file is re-read whenever its modification time changes.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ..config import get_settings

log = logging.getLogger(__name__)

_cache_path: Path | None = None
_cache_mtime: float | None = None
_cache_rules: list[tuple[re.Pattern[str], str, list[str]]] = []


def _compile(key: str) -> re.Pattern[str]:
    words = [re.escape(w) for w in key.strip().lower().split()]
    if not words:
        return re.compile(r"(?!x)x")  # never matches
    # Allow a plural suffix on the final word ("bus" -> "buses", "bike lane" -> "bike lanes").
    words[-1] = words[-1] + r"(?:e?s)?"
    pattern = r"\b" + r"\s+".join(words) + r"\b"
    return re.compile(pattern, re.IGNORECASE)


def parse_hints(data: object) -> list[tuple[re.Pattern[str], str, list[str]]]:
    rules: list[tuple[re.Pattern[str], str, list[str]]] = []
    if not isinstance(data, dict):
        log.warning("prompt hints file must contain a JSON object; ignoring")
        return rules
    for key, value in data.items():
        if not isinstance(key, str) or key.startswith("_") or not key.strip():
            continue
        if isinstance(value, str):
            texts = [value.strip()] if value.strip() else []
        elif isinstance(value, list):
            texts = [str(v).strip() for v in value if str(v).strip()]
        else:
            log.warning("prompt hint %r has unsupported value type %s; ignoring", key, type(value).__name__)
            continue
        if texts:
            rules.append((_compile(key), key, texts))
    return rules


def load_hints(path: Path | None = None) -> list[tuple[re.Pattern[str], str, list[str]]]:
    """Return the compiled rules, re-reading the file if it changed."""
    global _cache_path, _cache_mtime, _cache_rules
    path = path or get_settings().resolved_prompt_hints_file
    try:
        mtime = path.stat().st_mtime
    except OSError:
        if _cache_path != path or _cache_rules:
            log.info("prompt hints file not found at %s; no extra guidance will be added", path)
        _cache_path, _cache_mtime, _cache_rules = path, None, []
        return _cache_rules
    if _cache_path == path and _cache_mtime == mtime:
        return _cache_rules
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = parse_hints(data)
        log.info("loaded %d prompt hint rules from %s", len(rules), path)
    except Exception as exc:
        log.warning("could not read prompt hints file %s: %s", path, exc)
        rules = []
    _cache_path, _cache_mtime, _cache_rules = path, mtime, rules
    return rules


def hints_for(prompt: str, path: Path | None = None) -> list[str]:
    """Guidance strings whose keyword appears in the prompt, in file order, de-duplicated."""
    out: list[str] = []
    seen: set[str] = set()
    for pattern, _key, texts in load_hints(path):
        if pattern.search(prompt):
            for t in texts:
                if t not in seen:
                    seen.add(t)
                    out.append(t)
    return out
