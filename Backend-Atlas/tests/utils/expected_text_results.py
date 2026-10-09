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

    "Quebec_Cities_Only":    ["Montréal", "Québec", "Trois-Rivières", "Sherbrooke", "Saguenay", "Rimouski", "Sept-Îles", "Chibougamau", "Kuujjuaq"],
}

# Total raw number of text zones that Florence is expected to detect (before rejection)
# Updated with actual detection counts returned by test_florence_raw_detection_count
MAP_EXPECTED_ZONE_DETECTION_COUNTS = {
    "Quebec_Traite1783": 37,
    "Quebec_1800": 23,
    "Degrade_Afrique": 21,
    "Quebec_1791": 24,
    "Progress_wehrmacht_lux_May_1940": 12,
    "Quebec_Cities_Only": 25,
    "Nouvelle-France1750": 55,
    "genocide_Monde": 11,
    "1775_Quebec_NordUSA": 15,
}


CARD_THRESHOLDS = {
    "Quebec_Traite1783": {"min_hit_rate": 85.7, "max_dist": 0.80},
    "Quebec_1800": {"min_hit_rate": 74.0, "max_dist": 0.50},
    "Degrade_Afrique": {"min_hit_rate": 25.0, "max_dist": 3.25},
    "Quebec_1791": {"min_hit_rate": 83.0, "max_dist": 0.95},
    "Progress_wehrmacht_lux_May_1940": {"min_hit_rate": 100.0, "max_dist": 0.20},
    "Quebec_Cities_Only": {"min_hit_rate": 100.0, "max_dist": 0.20},
    "Nouvelle-France1750": {"min_hit_rate": 62.0, "max_dist": 1.50}, 
    "genocide_Monde": {"min_hit_rate": 100.0, "max_dist": 0.26},
    "1775_Quebec_NordUSA": {"min_hit_rate": 68.8, "max_dist": 0.63},
}
