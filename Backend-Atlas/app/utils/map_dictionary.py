import re
import unicodedata

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

    import difflib

    # 2. RECHERCHE DANS LE DICTIONNAIRE (Exacte puis similaire)
    matched_word = None

    # Construire un dictionnaire de clés simplifiées pour la recherche
    dict_keys_no_accents = {}
    for dict_word, (original_cased, category) in MAP_DICTIONARY_FLAT.items():
        dict_no_accents = remove_accents(dict_word)
        dict_keys_no_accents[dict_no_accents] = (original_cased, category)

    # A) Tentative de correspondance exacte (très rapide)
    if text_no_accents in dict_keys_no_accents:
        matched_word = dict_keys_no_accents[text_no_accents]
    elif text_hyphenated in dict_keys_no_accents:
        matched_word = dict_keys_no_accents[text_hyphenated]
    else:
        # B) Si échoue, utiliser difflib (intégré à Python, pas besoin de rapidfuzz)
        # On baisse le seuil à 75% (0.75) pour tolérer les fautes de frappe de Florence
        close_matches = difflib.get_close_matches(
            text_no_accents, dict_keys_no_accents.keys(), n=1, cutoff=0.75
        )
        if close_matches:
            matched_word = dict_keys_no_accents[close_matches[0]]

    if matched_word:
        original_cased, category = matched_word
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
