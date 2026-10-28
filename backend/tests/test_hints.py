import json
from pathlib import Path

from app.ai import hints
from app.ai.prompts import create_prompt, refine_prompt
from app.config import BACKEND_DIR


def _write(tmp_path: Path, data) -> Path:
    p = tmp_path / "hints.json"
    p.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return p


def test_keyword_matching_is_whole_word_case_insensitive_with_plurals(tmp_path):
    p = _write(
        tmp_path,
        {
            "_comment": "ignored",
            "bus": "outermost lanes",
            "bike lane": "green paint",
            "tree": ["row along kerb", "cast shadows"],
        },
    )
    assert hints.hints_for("Add BUS lanes here", p) == ["outermost lanes"]
    assert hints.hints_for("more buses please", p) == ["outermost lanes"]
    assert hints.hints_for("open a new business", p) == []  # 'bus' must be a whole word
    assert hints.hints_for("protected bike lanes on both sides", p) == ["green paint"]
    assert hints.hints_for("plant trees", p) == ["row along kerb", "cast shadows"]
    assert hints.hints_for("replace with housing", p) == []


def test_multiple_keywords_keep_file_order_and_dedupe(tmp_path):
    p = _write(tmp_path, {"bus": "A", "tree": "B", "bus lane": "A"})
    assert hints.hints_for("bus lane with trees", p) == ["A", "B"]


def test_missing_or_malformed_file_yields_no_hints(tmp_path):
    assert hints.hints_for("add bus lanes", tmp_path / "nope.json") == []
    bad = _write(tmp_path, "{not json")
    assert hints.hints_for("add bus lanes", bad) == []
    notobj = _write(tmp_path, ["bus"])
    assert hints.hints_for("add bus lanes", notobj) == []


def test_file_is_reloaded_when_changed(tmp_path):
    p = _write(tmp_path, {"bus": "v1"})
    assert hints.hints_for("bus", p) == ["v1"]
    import os
    import time

    p.write_text(json.dumps({"bus": "v2"}), encoding="utf-8")
    os.utime(p, (time.time() + 5, time.time() + 5))  # force a different mtime
    assert hints.hints_for("bus", p) == ["v2"]


def test_prompts_include_guidance_block():
    text = create_prompt("add bus lanes", "mask", ["Bus lanes use the outermost lanes."])
    assert "Design guidance from the planning team" in text
    assert "1. Bus lanes use the outermost lanes." in text
    assert text.index("Design guidance") < text.index('Instruction from a resident: "add bus lanes"')
    assert "Design guidance" not in create_prompt("add bus lanes", "mask", [])

    ref = refine_prompt("add trees", ["add bus lanes"], "text", ["Trees in a row."])
    assert "1. Trees in a row." in ref and "1. add bus lanes" in ref


def test_shipped_hints_file_is_valid_and_matches_bus():
    shipped = BACKEND_DIR / "prompt_hints.json"
    assert shipped.exists()
    got = hints.hints_for("add bus lanes to this road", shipped)
    assert any("outermost" in h for h in got)
