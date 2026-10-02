# fmt: off
# ruff: noqa
MAP_EXPECTED_TEXTS = {
    "1775_Quebec_NordUSA":  ["Québec", "Montréal", "Saint-Jean", "Boston"],

    "genocide_Monde":       ["Srebrenica"],

    "Nouvelle-France1750": ["Québec", "Trois-Rivières", "Montréal", "Boston", "New York", 
                            "Philadelphie", "Baltimore", "Charleston", "Savannah", 
                            "Baton Rouge", "Mobile", "Biloxi", "La Nouvelle-Orléans"],

    "Progress_wehrmacht_lux_May_1940": ["Vianden", "Ettelbrück", "Larochette", "Echternach", "Mersch", "Luxemburg"],

    "Quebec_1791":          ["Québec", "Montréal", "Kingston", "Toronto", "Boston", "New York"], 

    "Quebec_1800":          ["Québec", "Montréal", "Boston", "New York"],

    "Quebec_Traite1783":    ["Saint-Pierre", "Québec", "Montréal", "Boston", "New York", "La Nouvelle-Orléans"],

    "Degrade_Afrique":      ["Dakar", "Abidjan", "Lomé", "Douala"],
}

# Total raw number of text zones that Florence is expected to detect (before rejection)
# Updated with actual detection counts returned by test_florence_raw_detection_count
MAP_EXPECTED_ZONE_DETECTION_COUNTS = {
    "1775_Quebec_NordUSA": 19,
    "genocide_Monde": 17,
    "Nouvelle-France1750": 66,
    "Progress_wehrmacht_lux_May_1940": 14,
    "Quebec_1791": 35,
    "Quebec_1800": 37,
    "Quebec_Traite1783": 44,
    "Degrade_Afrique": 31,
}

CARD_THRESHOLDS = {
    "Quebec_1800.png": {"min_hit_rate": 74.0, "max_dist": 0.50},
    "Progress_wehrmacht_lux_May_1940.jpg": {"min_hit_rate": 100.0, "max_dist": 0.19},
    "genocide_Monde.png": {"min_hit_rate": 100.0, "max_dist": 0.26},
    "Quebec_Traite1783.png": {"min_hit_rate": 85.7, "max_dist": 0.80},
    "Degrade_Afrique.png": {"min_hit_rate": 65.2, "max_dist": 1.48},
    "Quebec_1791.png": {"min_hit_rate": 85.2, "max_dist": 0.51},
    "Nouvelle-France1750.png": {"min_hit_rate": 73.9, "max_dist": 1.20},
    "1775_Quebec_NordUSA.png": {"min_hit_rate": 68.8, "max_dist": 0.63},
}

# fmt: on
