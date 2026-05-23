"""
Text safety utilities for render-bound and user-visible AI text.

FFmpeg drawtext can fail on unsupported emoji or unusual Unicode glyphs,
especially on Windows font stacks. MIMIC defaults to professional, render-safe
text: plain ASCII, readable punctuation, and no emoji.
"""

import re
import unicodedata
from typing import Any, Dict, List


SAFE_TEXT_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?#@%&*()-_=+[]{}|;~/$")


def strip_emoji_and_symbols(value: str) -> str:
    """Remove emoji, pictographs, variation selectors, and unsupported symbols."""
    if not value:
        return ""

    normalized = unicodedata.normalize("NFKD", str(value))
    cleaned: List[str] = []

    for char in normalized:
        code = ord(char)
        category = unicodedata.category(char)

        if code in (0xFE0E, 0xFE0F, 0x200D):
            continue
        if 0x1F000 <= code <= 0x1FAFF:
            continue
        if 0x2600 <= code <= 0x27BF:
            continue
        if category in {"So", "Cs", "Co", "Cn"}:
            continue

        cleaned.append(char)

    return "".join(cleaned)


def sanitize_plain_text(value: Any, max_length: int = 2000) -> str:
    """Return professional, render-safe text with emoji and unsafe glyphs removed."""
    text = strip_emoji_and_symbols(str(value or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("-", "-").replace("–", "-").replace("->", "->")
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = "".join(char if char in SAFE_TEXT_CHARS or char == "\n" else " " for char in text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_length]


def sanitize_ffmpeg_text(value: Any, max_length: int = 240) -> str:
    """Sanitize text for FFmpeg drawtext's text= argument."""
    text = sanitize_plain_text(value, max_length=max_length)
    text = text.replace(":", "").replace(",", "").replace("'", "").replace('"', "").replace("\\", "")
    return "".join(char for char in text if char.isascii() and (char.isalnum() or char in " .!?#@%&*()-_=+[]{}|;~/$"))


def sanitize_text_event(event: Any) -> Any:
    """Return a sanitized copy/dict for a timed text event."""
    if isinstance(event, dict):
        next_event = dict(event)
        next_event["content"] = sanitize_plain_text(next_event.get("content", ""), max_length=160)
        return next_event

    if hasattr(event, "model_copy"):
        return event.model_copy(update={
            "content": sanitize_plain_text(getattr(event, "content", ""), max_length=160)
        })

    return event


def sanitize_blueprint_text_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize AI-generated blueprint text fields before validation/render."""
    if not isinstance(data, dict):
        return data

    for key, limit in {
        "text_overlay": 160,
        "narrative_message": 300,
        "plan_summary": 500,
        "arc_description": 500,
        "pacing_feel": 120,
        "visual_balance": 120,
    }.items():
        if key in data:
            data[key] = sanitize_plain_text(data.get(key, ""), max_length=limit)

    if isinstance(data.get("text_events"), list):
        data["text_events"] = [sanitize_text_event(event) for event in data["text_events"]]

    if isinstance(data.get("segments"), list):
        for segment in data["segments"]:
            if not isinstance(segment, dict):
                continue
            for key in ("vibe", "reasoning", "emotional_guidance"):
                if key in segment:
                    segment[key] = sanitize_plain_text(segment.get(key, ""), max_length=280)

    return data

