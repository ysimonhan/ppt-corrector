from __future__ import annotations

import copy
import difflib
from typing import Any

from lxml.etree import SubElement


DEFAULT_HIGHLIGHT_COLOR = "FFFF00"
_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def normalize_highlight_color(color_hex: str) -> str:
    color = color_hex.strip().lstrip("#").upper()
    if len(color) != 6 or any(char not in "0123456789ABCDEF" for char in color):
        raise ValueError("Highlight color must be a 6-character hex RGB string.")
    return color


def _highlight_run_xml(r_elem: Any, color_hex: str) -> None:
    """Apply highlight marker to a raw <a:r> lxml element."""
    r_pr = r_elem.find(f"{_A_NS}rPr")
    if r_pr is None:
        r_pr = SubElement(r_elem, f"{_A_NS}rPr")
        r_elem.remove(r_pr)
        r_elem.insert(0, r_pr)

    for existing in r_pr.findall(f"{_A_NS}highlight"):
        r_pr.remove(existing)

    highlight = SubElement(r_pr, f"{_A_NS}highlight")
    srgb = SubElement(highlight, f"{_A_NS}srgbClr")
    srgb.set("val", color_hex)


def _clone_run(r_elem: Any, new_text: str) -> Any:
    """Deep-copy a run element and set its text, preserving all formatting."""
    new_run = copy.deepcopy(r_elem)
    text_element = new_run.find(f"{_A_NS}t")
    if text_element is not None:
        text_element.text = new_text
    return new_run


def diff_segments(original: str, corrected: str) -> list[tuple[str, bool]]:
    """Word-level diff returning segments with a changed flag."""
    original_words = original.split()
    corrected_words = corrected.split()

    matcher = difflib.SequenceMatcher(None, original_words, corrected_words)
    segments: list[tuple[str, bool]] = []

    for operation, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if operation == "equal":
            text = " ".join(corrected_words[j1:j2])
            segments.append((text, False))
        elif j1 < j2:
            text = " ".join(corrected_words[j1:j2])
            segments.append((text, True))

    result: list[tuple[str, bool]] = []
    for index, (text, changed) in enumerate(segments):
        if index < len(segments) - 1:
            text += " "
        result.append((text, changed))

    return result


def apply_correction_to_runs_highlighted(paragraph: Any, corrected_text: str, color_hex: str) -> None:
    """Apply corrected text back to runs, highlighting only changed words."""
    runs = list(paragraph.runs)
    if not runs:
        return

    original_text = "".join(run.text for run in runs)
    if original_text.strip() == corrected_text.strip():
        return

    segments = diff_segments(original_text, corrected_text)
    template_run = runs[0]._r

    new_run_elements = []
    for segment_text, is_changed in segments:
        if not segment_text:
            continue
        new_run = _clone_run(template_run, segment_text)
        if is_changed:
            _highlight_run_xml(new_run, color_hex)
        new_run_elements.append(new_run)

    paragraph_element = paragraph._p
    for run in runs:
        paragraph_element.remove(run._r)

    for new_run in new_run_elements:
        paragraph_element.append(new_run)

