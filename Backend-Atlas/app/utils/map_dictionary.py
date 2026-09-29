import re
import unicodedata

from .map_dictionary_data import (
    ENGLISH_FLORENCE_TO_FRENCH_TRANSLATIONS,
    MAP_DICTIONARY_CATEGORIZED,
)

import difflib

MAP_DICTIONARY_FLAT = {}
for category, words in MAP_DICTIONARY_CATEGORIZED.items():
    for w in words:
        MAP_DICTIONARY_FLAT[w.lower()] = (w, category)


def remove_accents(input_str: str) -> str:
    nfkd_form = unicodedata.normalize("NFKD", input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


DICT_KEYS_NO_ACCENTS = {}
for dict_word, (original_cased, category) in MAP_DICTIONARY_FLAT.items():
    dict_no_accents = remove_accents(dict_word)
    DICT_KEYS_NO_ACCENTS[dict_no_accents] = (original_cased, category)


def apply_map_dictionary_correction(text: str) -> tuple[str, str]:
    text_clean = text.strip()
    if not text_clean:
        return "", "other"

    text_lower = text_clean.lower()

    for eng_phrase, fr_phrase in ENGLISH_FLORENCE_TO_FRENCH_TRANSLATIONS.items():
        if " " in eng_phrase and eng_phrase in text_lower:
            text_clean = re.sub(re.escape(eng_phrase), fr_phrase, text_clean, flags=re.IGNORECASE)

    text_clean_for_match = re.sub(r"[\d\(\)]", "", text_clean).strip()

    text_no_accents = remove_accents(text_clean_for_match.lower())
    text_hyphenated = re.sub(r"[\s\n]+", "-", text_no_accents)

    matched_word = None

    if text_no_accents in DICT_KEYS_NO_ACCENTS:
        matched_word = DICT_KEYS_NO_ACCENTS[text_no_accents]
    elif text_hyphenated in DICT_KEYS_NO_ACCENTS:
        matched_word = DICT_KEYS_NO_ACCENTS[text_hyphenated]
    else:
        close_matches = difflib.get_close_matches(text_no_accents, DICT_KEYS_NO_ACCENTS.keys(), n=1, cutoff=0.75)
        if close_matches:
            matched_word = DICT_KEYS_NO_ACCENTS[close_matches[0]]

    if matched_word:
        original_cased, category = matched_word

        alpha_count = sum(1 for c in text_clean if c.isalpha())
        upper_count = sum(1 for c in text_clean if c.isupper())

        # Force uppercase if the extracted text is >= 80% uppercase (e.g. MAURITAnNE)
        if alpha_count > 0 and (upper_count / alpha_count) >= 0.8:
            corrected_text = original_cased.upper()
        else:
            corrected_text = original_cased

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
                if text_clean.count("\n") == 1 and corrected_text.count(" ") == 1:
                    corrected_text = corrected_text.replace(" ", "\n")

        return corrected_text, category

    return text_clean, "rejet"
