"""Indian vehicle registration-number normalization.

Converts messy OCR output (``"TS 09 AB 1234"``, ``"ts-09-ab-1234"``,
``"TSO9ABI234"``) into the canonical compact form ``"TS09AB1234"``.

Corrections are position-aware: a character is only "fixed" when the slot it
occupies in the expected ``[letters][digits][letters][digits]`` layout
demands a different character class, using a small, well-known set of
OCR confusions. We never blindly rewrite a character everywhere in the
string.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from typing import List, Optional

# Standard Indian plate layout: SS DD LLL DDDD (state, RTO code, series, number)
PLATE_REGEX = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}$")

_ALLOWED_CHARS = re.compile(r"[^A-Z0-9]")

# OCR confusions: digit glyph <-> letter glyph
DIGIT_TO_LETTER = {"0": "O", "1": "I", "8": "B", "5": "S", "2": "Z"}
LETTER_TO_DIGIT = {"O": "0", "I": "1", "B": "8", "S": "5", "Z": "2"}

# Letter-to-letter OCR confusions: rare/uncommon letter is the key,
# likely-intended letter is the value.  "O" is almost never used on
# Indian plates in letter segments, but "D" is common — OCR frequently
# misreads D as O because the glyphs are nearly identical.
# Similarly, "I" is almost never used on Indian plates (skipped to avoid
# confusion with "1"), but "T" is very common (TN, TS, TR, etc.).
LETTER_CONFUSIONS = {"O": "D", "I": "T"}

# Valid Indian state code prefixes (first 2 letters of a plate).
# Used to prefer "OD" (Odisha) over "OO" when OCR misreads D as O.
VALID_STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CH", "DD", "DL", "GA", "GJ",
    "HR", "HP", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML",
    "MN", "MP", "MZ", "NL", "OD", "PB", "PY", "RJ", "SK", "TN",
    "TS", "TR", "UK", "UP", "WB",
}

# Preferred segment-length combinations (state=2 is fixed), ordered by how
# common they are on real Indian plates so the first valid match wins.
_SEGMENT_LENGTH_PREFERENCE = [
    (2, 2, 2, 4),
    (2, 2, 3, 4),
    (2, 2, 1, 4),
    (2, 1, 2, 4),
    (2, 2, 2, 3),
    (2, 1, 1, 4),
    (2, 2, 3, 3),
    (2, 1, 2, 3),
    (2, 2, 1, 3),
    (2, 2, 2, 2),
    (2, 1, 3, 4),
]


@dataclass
class NormalizationResult:
    raw: str
    normalized: str
    is_valid_format: bool


def _clean(raw: str) -> str:
    return _ALLOWED_CHARS.sub("", raw.upper())


def _fix_letters(segment: str) -> List[str]:
    """Return all plausible letter-segment corrections.

    When a character is ambiguous (e.g. OCR read "O" but the real
    character might be "D"), every combination is generated so the
    caller can try each against the plate regex.
    """
    options: List[List[str]] = []
    for ch in segment:
        if ch.isalpha():
            opts = [ch]
            if ch in LETTER_CONFUSIONS:
                opts.append(LETTER_CONFUSIONS[ch])
            options.append(opts)
        elif ch in DIGIT_TO_LETTER:
            opts = [DIGIT_TO_LETTER[ch]]
            # "0" in a letter segment could also be "D" — OCR frequently
            # misreads D as 0 because the glyphs are nearly identical.
            if ch == "0":
                opts.append("D")
            options.append(opts)
        else:
            return []
    return ["".join(combo) for combo in product(*options)]


def _fix_digits(segment: str) -> Optional[str]:
    fixed = []
    for ch in segment:
        if ch.isdigit():
            fixed.append(ch)
        elif ch in LETTER_TO_DIGIT:
            fixed.append(LETTER_TO_DIGIT[ch])
        else:
            return None
    return "".join(fixed)


def normalize_vehicle_number(raw: Optional[str]) -> NormalizationResult:
    """Normalize a raw OCR string into the canonical Indian plate format.

    Falls back to the cleaned (uppercased, stripped) string when no
    position-aware correction produces a fully valid plate, rather than
    forcing an incorrect guess.
    """
    if not raw:
        return NormalizationResult(raw=raw or "", normalized="", is_valid_format=False)

    cleaned = _clean(raw)

    total_len = len(cleaned)
    best_candidate: Optional[str] = None
    best_score = -1

    for seg_idx, (state_len, district_len, series_len, number_len) in enumerate(_SEGMENT_LENGTH_PREFERENCE):
        if state_len + district_len + series_len + number_len != total_len:
            continue

        i = 0
        state_raw = cleaned[i : i + state_len]
        i += state_len
        district_raw = cleaned[i : i + district_len]
        i += district_len
        series_raw = cleaned[i : i + series_len]
        i += series_len
        number_raw = cleaned[i : i + number_len]

        states = _fix_letters(state_raw)
        district = _fix_digits(district_raw)
        series_list = _fix_letters(series_raw)
        number = _fix_digits(number_raw)

        if not states or district is None or not series_list or number is None:
            continue

        for state, series in product(states, series_list):
            candidate = f"{state}{district}{series}{number}"
            if not PLATE_REGEX.match(candidate):
                continue
            # Score: prefer valid state codes, and only prefer D over O
            # and T over I in the series when the state code is valid (high
            # confidence that the plate is Indian and O/I are misreads).
            score = (len(_SEGMENT_LENGTH_PREFERENCE) - seg_idx) * 100
            if state in VALID_STATE_CODES:
                score += 2
                score += sum(1 for ch in series if ch not in ("O", "I"))
            if score > best_score:
                best_score = score
                best_candidate = candidate

    if best_candidate is not None:
        return NormalizationResult(raw=raw, normalized=best_candidate, is_valid_format=True)

    # No valid reconstruction found - return the cleaned string as-is so the
    # caller can still surface it (with a low-confidence warning upstream).
    return NormalizationResult(raw=raw, normalized=cleaned, is_valid_format=False)


def is_valid_indian_plate(value: str) -> bool:
    return bool(PLATE_REGEX.match(value or ""))


def clean_vehicle_number(value: str) -> str:
    """Uppercase + strip separators only - no OCR confusion correction.

    Used for manually-entered/looked-up plates (e.g. path params, search
    boxes) where guessing character substitutions would be inappropriate;
    OCR-derived text should go through :func:`normalize_vehicle_number`
    instead.
    """
    return _clean(value or "")
