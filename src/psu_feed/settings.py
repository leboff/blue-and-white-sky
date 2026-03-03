"""
JSON-backed settings for keywords and authority accounts.
Load/save data/settings.json; reload updates in-memory state and compiled regex patterns.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _get_settings_path() -> Path:
    """Lazy path to avoid circular import with config."""
    from .config import DATABASE_PATH
    return DATABASE_PATH.parent / "settings.json"

# Defaults for seeding when settings.json is missing (must match original filter/authority_dids)
DEFAULT_KEYWORDS = [
    r"\bWe\s?Are\b",
    r"Nittany\s?Lions?",
    r"Beaver\s?Stadium",
    r"Happy\s?Valley",
    r"White\s?Out",
    r"Nittanyville",
    r"Blue-White\s?Game",
    r"\bLBU\b",
    r"Linebacker\s?U",
    r"Penn\s?State",
    r"\bPSU\b",
    r"James\s?Franklin",
    r"Matt\s?Campbell",
    r"Taylor\s?Mouser",
    r"D'?Anton\s?Lynn",
    r"Terry\s?Smith",
    r"Deon\s?Broomfield",
    r"Tony\s?Rojas",
    r"Rocco\s?Becht",
    r"Anthony\s?Donkoh",
    r"Cooper\s?Cousins",
    r"Daryus\s?Dixson",
    r"Max\s?Granville",
    r"Caleb\s?Bacon",
    r"James\s?Peoples",
    r"Peyton\s?Falzone",
    r"Saquon\s?Barkley",
    r"Micah\s?Parsons",
    r"Trace\s?McSorley",
    r"Jahan\s?Dotson",
    r"Olu\s?Fashanu",
    r"LaVar\s?Arrington",
    r"Paul\s?Posluszny",
    r"Jack\s?Ham",
    r"Franco\s?Harris",
    r"Penn\s?State\s?Football",
    r"PSU\s?Football",
    r"Big\s?Ten\s?Football",
]
DEFAULT_NEGATIVE_KEYWORDS = [
    r"Power\s?Supply",
    r"Modular",
    r"850W",
    r"750W",
    r"1000W",
    r"Gold\s?Rated",
    r"Voltage",
    r"Corsair",
    r"EVGA",
    r"Portland\s?State",
    r"Plymouth\s?State",
    r"PC\s?Build",
    r"Canada",
]
DEFAULT_AUTHORITIES = [
    {"did": "did:plc:x5ogzhccdzixduafk7za2arb", "label": "Daniel Gallen"},
    {"did": "did:plc:f7i33cd3b5n6en2iunk2mwkp", "label": "Bill DiFilippo"},
    {"did": "did:plc:rk7w4mhlnjr6paz7qjpn6fyt", "label": "Thomas Frank Carr"},
    {"did": "did:plc:mk6xp2py63mhfqsycqyoi56n", "label": "Penn State Football (Official)"},
    {"did": "did:plc:xy4gk3zyicyrohhydm76zkvi", "label": "Roar Lions Roar"},
    {"did": "did:plc:mrftqkimm2yrs4lqgelgxykd", "label": "On3"},
    {"did": "did:plc:kbrmj4uhmko7arfn7xiev4zu", "label": "Jon Sauber"},
]

# Module-level state (updated by load_settings / reload_settings)
_keywords: list[str] = []
_negative_keywords: list[str] = []
_authorities: list[dict[str, str]] = []
_authority_dids: set[str] = set()
_positive_pattern: re.Pattern[str] | None = None
_negative_pattern: re.Pattern[str] | None = None
_settings_mtime: float = 0.0


def _compile_patterns() -> None:
    global _positive_pattern, _negative_pattern
    if _keywords:
        _positive_pattern = re.compile("|".join(_keywords), re.IGNORECASE)
    else:
        _positive_pattern = re.compile("(?!)")  # never matches
    if _negative_keywords:
        _negative_pattern = re.compile("|".join(_negative_keywords), re.IGNORECASE)
    else:
        _negative_pattern = re.compile("(?!)")


def _build_authority_dids() -> None:
    global _authority_dids
    _authority_dids = {a["did"] for a in _authorities if a.get("did")}


def load_settings() -> dict[str, Any]:
    """Load from JSON; if file missing, seed from defaults and return."""
    global _keywords, _negative_keywords, _authorities, _settings_mtime
    path = _get_settings_path()
    if not path.exists():
        data = {
            "keywords": DEFAULT_KEYWORDS,
            "negative_keywords": DEFAULT_NEGATIVE_KEYWORDS,
            "authorities": DEFAULT_AUTHORITIES,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        _settings_mtime = path.stat().st_mtime
        _keywords = list(DEFAULT_KEYWORDS)
        _negative_keywords = list(DEFAULT_NEGATIVE_KEYWORDS)
        _authorities = list(DEFAULT_AUTHORITIES)
        _compile_patterns()
        _build_authority_dids()
        return data
    with open(path) as f:
        data = json.load(f)
    _settings_mtime = path.stat().st_mtime
    _keywords = data.get("keywords") or []
    _negative_keywords = data.get("negative_keywords") or []
    _authorities = data.get("authorities") or []
    if not _keywords and not _negative_keywords and not _authorities:
        _keywords = list(DEFAULT_KEYWORDS)
        _negative_keywords = list(DEFAULT_NEGATIVE_KEYWORDS)
        _authorities = list(DEFAULT_AUTHORITIES)
    _compile_patterns()
    _build_authority_dids()
    return data


def reload_settings() -> None:
    """Re-read JSON and update in-memory state and patterns."""
    path = _get_settings_path()
    if not path.exists():
        load_settings()
        return
    with open(path) as f:
        data = json.load(f)
    global _keywords, _negative_keywords, _authorities, _settings_mtime
    _settings_mtime = path.stat().st_mtime
    _keywords = data.get("keywords") or []
    _negative_keywords = data.get("negative_keywords") or []
    _authorities = data.get("authorities") or []
    _compile_patterns()
    _build_authority_dids()


def reload_if_changed() -> None:
    """If settings file mtime changed, reload. Call periodically from ingester."""
    path = _get_settings_path()
    if not path.exists():
        return
    try:
        mtime = path.stat().st_mtime
        if mtime != _settings_mtime:
            reload_settings()
    except OSError:
        pass


def save_settings(data: dict[str, Any]) -> None:
    """Write JSON and reload in-memory state."""
    path = _get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    reload_settings()


def _ensure_loaded() -> None:
    if _positive_pattern is None:
        load_settings()


def get_keywords() -> list[str]:
    _ensure_loaded()
    return list(_keywords)


def get_negative_keywords() -> list[str]:
    _ensure_loaded()
    return list(_negative_keywords)


def get_authorities() -> list[dict[str, str]]:
    _ensure_loaded()
    return list(_authorities)


def get_authority_dids() -> set[str]:
    _ensure_loaded()
    return set(_authority_dids)


def get_authority_accounts() -> list[tuple[str, str]]:
    """Return list of (did, label) for backward compatibility."""
    auth = get_authorities()
    return [(a["did"], a.get("label") or a["did"]) for a in auth if a.get("did")]


def get_compiled_positive_pattern() -> re.Pattern[str]:
    if _positive_pattern is None:
        load_settings()
    return _positive_pattern or re.compile("(?!)")


def get_compiled_negative_pattern() -> re.Pattern[str]:
    if _negative_pattern is None:
        load_settings()
    return _negative_pattern or re.compile("(?!)")


def is_relevant_post(text: str) -> bool:
    """True if the post matches PSU football keywords and passes negative filter."""
    if not text or not text.strip():
        return False
    if not get_compiled_positive_pattern().search(text):
        return False
    if get_compiled_negative_pattern().search(text):
        return False
    return True


# Ensure state is populated on first import
load_settings()
