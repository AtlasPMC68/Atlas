# fmt: off
# ruff: noqa

# Every text each map should give once the OCR is done: its labels, its legend lines,
# then its title. A label split over several lines is one text ("TERRE- / NEUVE" is
# "Terre-Neuve"), but each language of a bilingual box is its own text, and so is each
# line of a title, as the detector reads them. Years are left out, the pipeline removes
# them. Left out on purpose, since the filter drops them: lines over 5 words, footnote
# numbers, compass letters and scale bars.
# Also left out, listed per map: the labels the detector cannot be expected to find,
# thin italic text drawn rotated or along a curve, pale on the water or the land.
# Only the maps listed here are tested: the other images of tests/assets are skipped
MAP_EXPECTED_TEXTS = {
    "Quebec_Cities_Only": [
        "Montréal", "Québec", "Trois-Rivières", "Sherbrooke", "Saguenay", "Rimouski", "Sept-Îles",
        "Chibougamau", "Kuujjuaq",
    ],

    "Communautes_cries": [
        "Whapmagoostui", "Chisasibi", "Wemindji", "Eastmain", "Nemaska", "Waskaganish", "Mistissini",
        "Oujé-Bougoumou", "Waswanipi",
        # Title
        "Communautés", "cries",
    ],

    "Sahel_Afrique": [
        "Algérie", "Mauritanie", "Mali", "Niger", "Sénégal", "Tchad", "Soudan", "Érythrée",
        "Burkina Faso", "Nigeria", "Éthiopie",
    ],

    # Left out: Fleuve St-Laurent, Rivière Chaudière, Richelieu, Rivière Kennebec, and the
    # Montgomery written vertically along its arrow. "(Mass.)" is a note under Maine, its own text
    "1775_Quebec_NordUSA": [
        "Province de Québec", "Québec", "Montgomery", "Arnold", "Montréal", "Saint-Jean", "Maine",
        "Mass.", "Fort Ticonderoga", "New Hampshire", "Océan Atlantique", "Boston",
        "Massachusetts",
    ],

    "Progress_wehrmacht_lux_May_1940": [
        "Belgium", "Germany", "France", "Luxemburg", "Vianden", "Ettelbrück", "Larochette", "Mersch",
        "Echternach", "2. PzD", "1. PzD", "10. PzD",
        # Title
        "Progress of the Wehrmacht", "during 10th May",
    ],

    "Nouvelle-France1750": [
        "Océan Pacifique", "Baie d'Hudson", "Canada", "Terre-Neuve", "Plaisance", "Isle St-Jean",
        "Isle Royale", "Louisbourg", "Acadie", "Port-Royal", "Tadoussac", "Québec", "Trois-Rivières",
        "Montréal", "Fort Richelieu", "Fort Chambly", "Pays d'en Hauts", "Fort Bourbon",
        "Fort Dauphin", "Fort La Reine", "Fort St-Pierre", "Fort Michillimakinac", "Fort Frontenac",
        "Fort Beauharnois", "Fort Détroit", "Fort Duquesne", "Haute-Louisiane", "Pays des Illinois",
        "Fort Orléans", "Fort St-Louis", "Fort de Chartres", "Louisiane", "Basse-Louisiane",
        "Fort Rosalie", "Fort Toulouse", "Baton Rouge", "Mobile", "Biloxi", "La Nouvelle-Orléans",
        "Golfe du Mexique", "Océan Atlantique", "Boston", "New York", "Philadelphie", "Baltimore",
        "Charleston", "Savannah",
        # Legend
        "Contrôle des territoires", "France", "Grande-Bretagne", "Espagne",
        # Title
        "La Nouvelle-France", "vers",
    ],
}

# Number of text blocks each map should give: one per expected text
MAP_EXPECTED_ZONE_DETECTION_COUNTS = {name: len(texts) for name, texts in MAP_EXPECTED_TEXTS.items()}

# The OCR may give this ratio of blocks more or less than expected (85 to 115 %)
COUNT_TOLERANCE_RATIO = 0.15

# Accuracy a map must reach in test_text_extraction_accuracy:
#   - min_hit_rate: % of the expected texts found
#   - max_dist: average character error of the expected texts, from 0 (exact) to 1 (missing)
DEFAULT_THRESHOLDS = {"min_hit_rate": 90.0, "max_dist": 0.20}

# Per map overrides of DEFAULT_THRESHOLDS
CARD_THRESHOLDS = {}
