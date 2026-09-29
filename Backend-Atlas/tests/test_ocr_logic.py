import pytest
import math
from app.utils.map_dictionary import apply_map_dictionary_correction, DICT_KEYS_NO_ACCENTS


def test_dictionary_accents():
    # Should correctly apply accents
    corrected, cat = apply_map_dictionary_correction("Quebec")
    assert corrected.lower() == "québec"


def test_dictionary_uppercase_retention():
    # >= 80% uppercase -> return uppercase
    corrected, cat = apply_map_dictionary_correction("QUEBEC")
    assert corrected == "QUÉBEC"

    corrected, cat = apply_map_dictionary_correction("QUeBEC")
    assert corrected == "QUÉBEC"


def test_dictionary_rejet():
    # Unknown word should be rejected
    corrected, cat = apply_map_dictionary_correction("RandomUnknownWord123")
    assert cat == "rejet"


def test_dictionary_difflib_cutoff():
    # Similar word should match
    corrected, cat = apply_map_dictionary_correction("Montral")
    assert corrected == "Montréal"


import sys
