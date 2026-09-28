import re
import unicodedata

from rapidfuzz import fuzz, process

from .map_dictionary_data import (
    ENGLISH_FLORENCE_TO_FRENCH_TRANSLATIONS,
    MAP_DICTIONARY_CATEGORIZED,
)

MAP_DICTIONARY_FLAT = {}
for category, words in MAP_DICTIONARY_CATEGORIZED.items():
    for w in words:
        MAP_DICTIONARY_FLAT[w.lower()] = (w, category)

import json
import logging
import os

logger = logging.getLogger(__name__)

CUSTOM_DICTIONARY_FILE = os.getenv("CUSTOM_DICTIONARY_FILE", "/data/user_dictionary_overrides.json")


def load_custom_dictionary() -> dict[str, dict]:
    """Load persistent custom dictionary overrides defined by users."""
    if os.path.exists(CUSTOM_DICTIONARY_FILE):
        try:
            with open(CUSTOM_DICTIONARY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load custom dictionary overrides: {e}")
            return {}
    return {}


def save_custom_dictionary_entry(
    raw_text: str, corrected_text: str, category: str, action: str = "keep"
) -> dict:
    """Save or update a learned user dictionary rule."""
    raw_key = raw_text.strip().lower()
    if not raw_key:
        return {}

    data = load_custom_dictionary()
    entry = {
        "raw_text": raw_text.strip(),
        "corrected_text": corrected_text.strip(),
        "category": category.strip(),
        "action": action.strip(),
    }
    data[raw_key] = entry

    try:
        os.makedirs(os.path.dirname(CUSTOM_DICTIONARY_FILE), exist_ok=True)
        with open(CUSTOM_DICTIONARY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save custom dictionary entry to {CUSTOM_DICTIONARY_FILE}: {e}")

    return entry


def remove_accents(input_str: str) -> str:
    nfkd_form = unicodedata.normalize("NFKD", input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def apply_map_dictionary_correction(text: str) -> tuple[str, str]:
    text_clean = text.strip()
    if not text_clean:
        return "", "other"

    text_lower = text_clean.lower()

    # 0. VÉRIFICATION DU DICTIONNAIRE PERSONNALISÉ DE L'UTILISATEUR
    custom_dict = load_custom_dictionary()
    if text_lower in custom_dict:
        entry = custom_dict[text_lower]
        if entry.get("action") == "ignore":
            return "", "ignored"
        chosen_cat = entry.get("category", "rejet")
        chosen_text = entry.get("corrected_text", text_clean)
        return chosen_text, chosen_cat

    # 1. TRADUCTION DES EXPRESSIONS (Pre-processing)
    for eng_phrase, fr_phrase in ENGLISH_FLORENCE_TO_FRENCH_TRANSLATIONS.items():
        if " " in eng_phrase and eng_phrase in text_lower:
            text_clean = re.sub(re.escape(eng_phrase), fr_phrase, text_clean, flags=re.IGNORECASE)

    # Remove digits and parentheses for dictionary matching so "Montréal (1642)" matches "Montréal"
    text_clean_for_match = re.sub(r"[\d\(\)]", "", text_clean).strip()
    
    text_no_accents = remove_accents(text_clean_for_match.lower())
    text_hyphenated = re.sub(r"[\s\n]+", "-", text_no_accents)

    choices = {remove_accents(k): k for k in MAP_DICTIONARY_FLAT.keys()}

    # RapidFuzz match
    match1 = process.extractOne(text_no_accents, choices.keys(), scorer=fuzz.ratio)
    match2 = process.extractOne(text_hyphenated, choices.keys(), scorer=fuzz.ratio)

    best_match = match1
    if match2 and (not match1 or match2[1] > match1[1]):
        best_match = match2

    if best_match and best_match[1] >= 80:  # Strict threshold to avoid hallucinations
        matched_dict_word_no_accents = best_match[0]
        original_lower = choices[matched_dict_word_no_accents]
        original_cased, category = MAP_DICTIONARY_FLAT[original_lower]

        corrected_text = original_cased
        if text.isupper():
            corrected_text = original_cased.upper()

        if "\n" in text_clean:
            # Preserve original whitespace if word counts match
            orig_tokens = re.split(r"(\s+)", text_clean)
            corr_tokens = re.split(r"(\s+)", corrected_text)

            if len(orig_tokens) == len(corr_tokens):
                res = []
                for o_w, c_w in zip(orig_tokens, corr_tokens):
                    if o_w.isspace():
                        res.append(o_w)
                    else:
                        res.append(c_w)
                corrected_text = "".join(res)
            else:
                # Fallback: if there is exactly 1 newline and 1 space
                if text_clean.count("\n") == 1 and corrected_text.count(" ") == 1:
                    corrected_text = corrected_text.replace(" ", "\n")

        return corrected_text, category

    return text_clean, "rejet"
