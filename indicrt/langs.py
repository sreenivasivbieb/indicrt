"""Language registry for Indic and South Asian languages."""

from __future__ import annotations

# code -> (English name, native name, aksharamukha script name or None)
LANGS: dict[str, tuple[str, str, str | None]] = {
    "hi": ("Hindi", "हिन्दी", "Devanagari"),
    "bn": ("Bengali", "বাংলা", "Bengali"),
    "ta": ("Tamil", "தமிழ்", "Tamil"),
    "te": ("Telugu", "తెలుగు", "Telugu"),
    "ml": ("Malayalam", "മലയാളം", "Malayalam"),
    "mr": ("Marathi", "मराठी", "Devanagari"),
    "gu": ("Gujarati", "ગુજરાતી", "Gujarati"),
    "kn": ("Kannada", "ಕನ್ನಡ", "Kannada"),
    "or": ("Odia", "ଓଡ଼ିଆ", "Oriya"),
    "ur": ("Urdu", "اردو", None),  # Perso-Arabic: no reliable romanizer bundled
    "ne": ("Nepali", "नेपाली", "Devanagari"),
    "pa": ("Punjabi", "ਪੰਜਾਬੀ", "Gurmukhi"),
    "as": ("Assamese", "অসমীয়া", "Assamese"),
    "en": ("English", "English", None),
}

NAME_TO_CODE = {v[0].lower(): k for k, v in LANGS.items()}
NAME_TO_CODE.update({"oriya": "or", "panjabi": "pa"})

# Languages where casual romanization usually drops the word-final inherent "a"
SCHWA_DELETION = {"hi", "mr", "ne", "pa", "gu", "bn"}


def to_code(name_or_code: str) -> str:
    s = (name_or_code or "").strip().lower()
    if s in LANGS:
        return s
    if s in NAME_TO_CODE:
        return NAME_TO_CODE[s]
    raise KeyError(f"Unknown language: {name_or_code!r}")


def name(code: str) -> str:
    return LANGS.get(code, (code, code, None))[0]


def parse_langs(arg: str | None) -> set[str] | None:
    if not arg or arg.strip().lower() in {"all", "*"}:
        return None
    return {to_code(x) for x in arg.split(",") if x.strip()}
