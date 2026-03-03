"""Keyword and heuristic filter for Penn State football posts."""

import re

# PSU Football Regex Keywords - 2026 Season
PSU_FOOTBALL_KEYWORDS = [
    # Identity & Phrases
    r"\bWe\s?Are\b",
    r"Nittany\s?Lions?",
    r"Beaver\s?Stadium",
    r"Happy\s?Valley",
    r"White\s?Out",
    r"Nittanyville",
    r"Blue-White\s?Game",
    r"\bLBU\b",
    r"Linebacker\s?U",
    # General (broad catch so we don't miss "Penn State" / "PSU" without "Football")
    r"Penn\s?State",
    r"\bPSU\b",
    # Current Coaching Staff (2026)
    r"Matt\s?Campbell",
    r"Taylor\s?Mouser",
    r"D'?Anton\s?Lynn",
    r"Terry\s?Smith",
    r"Deon\s?Broomfield",
    # Key Players & Rising Stars (2026 Roster)
    r"Tony\s?Rojas",
    r"Rocco\s?Becht",
    r"Anthony\s?Donkoh",
    r"Cooper\s?Cousins",
    r"Daryus\s?Dixson",
    r"Max\s?Granville",
    r"Caleb\s?Bacon",
    r"James\s?Peoples",
    r"Peyton\s?Falzone",
    # Legends & Pro Lions
    r"Saquon\s?Barkley",
    r"Micah\s?Parsons",
    r"Trace\s?McSorley",
    r"Jahan\s?Dotson",
    r"Olu\s?Fashanu",
    r"LaVar\s?Arrington",
    r"Paul\s?Posluszny",
    r"Jack\s?Ham",
    r"Franco\s?Harris",
    # General Program
    r"Penn\s?State\s?Football",
    r"PSU\s?Football",
    r"Big\s?Ten\s?Football",
]

# Negative Keywords (filter out "Power Supply Unit" and other noise)
PSU_NEGATIVE_KEYWORDS = [
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
]

# Compile patterns once for efficiency
POSITIVE_PATTERN = re.compile("|".join(PSU_FOOTBALL_KEYWORDS), re.IGNORECASE)
NEGATIVE_PATTERN = re.compile("|".join(PSU_NEGATIVE_KEYWORDS), re.IGNORECASE)


def is_relevant_post(text: str) -> bool:
    """True if the post matches PSU football keywords and passes negative filter."""
    if not text or not text.strip():
        return False
    if not POSITIVE_PATTERN.search(text):
        return False
    if NEGATIVE_PATTERN.search(text):
        return False
    return True
