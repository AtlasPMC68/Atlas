# fmt: off
# ruff: noqa
MAP_EXPECTED_TEXTS = {
    "1775_Quebec_NordUSA":  ["PROVINCE\nDE QUÉBEC", "Fleuve St-Laurent", "Québec", "Montgomery", "Rivière Chaudière",
                            "Arnold", "Montréal", "Rivière Richelieu", "Saint-Jean", "Rivière Kennebec", "MAINE\n(MASS.)",
                            "Fort Ticonderoga", "NEW\nHAMPSHIRE", "OCÉAN\nATLANTIQUE", "Boston", "MASSACHUSETTS"],

    "genocide_Monde":       ["Canada", "Holodomor", "Holocauste\nHolocaust", "Srebrenica", "Arménie\nArmenia", "Rwanda",
                            "Cambodge\nCambodia", "Namibie\nNamibia"],

    "Nouvelle-France1750": ["Baie\nd'Hudson", "Fort Bourbon", "Fort Dauphin", "Fort La Reine", "Pays d'en Hauts", 
                            "CANADA", "Terre-\nNeuve", "Plaisance (1662)", "Tadoussac (1600)", "Isle St-Jean", 
                            "Isle Royale", "Louisbourg (1719)", "Fort St-Pierre", "Québec (1608)", "Trois-Rivières (1634)",
                            "Montréal (1642)", "ACADIE", "Fort Richelieu", "Port-Royal (1605)", "Fort Chambly",
                            "Fort Beauharnois", "Fort Michilimakinac", "Fort Frontenac", "Fort Détroit", "Boston (1630)",
                            "New York (1626)", "Fort Duquesne", "Haute-Louisiane\n(Pays des Illinois)", 
                            "Philadelphie (1681)", "Baltimore (1729)", "Fort Orléans", "Fort de Chartres", 
                            "Fort St-Louis", "Océan\nAtlantique", "LOUISIANE", "Basse-\nLouisiane", "Charleston (1680)",
                            "Savannah (1733)", "Fort Rosalie", "Fort Toulouse", "Baton Rouge (1720)", "Mobile (1702)",
                            "Biloxi (1699)", "La Nouvelle-Orléans (1718)", "Golfe du Mexique", "Océan\nPacifique"],

    "Progress_wehrmacht_lux_May_1940": ["Belgium", "Germany", "2. PzD", "Vianden", "1. PzD", "Ettelbrück", "Larochette", 
                                        "10. PzD", "Echternach", "Mersch", "Luxemburg", "France"],

    "Quebec_1791":          ["Mer du Labrador", "Baie\nd'Hudson", "TERRE DE RUPERT", "TERRE-\nNEUVE", "BAS-CANADA", "HAUT-CANADA",
                            "Lac Supérieur", "Québec", "Fleuve Saint-Laurent", "ÎLE\nSAINT-\nJEAN", "ÎLE DU\nCAP-\nBRETON", 
                            "NOUVEAU-\nBRUNSWICK", "Montréal", "NOUVELLE-\nÉCOSSE", "OCÉAN\nATLANTIQUE", "Lac Michigan", "Lac Huron",
                            "Kingston", "Lac Ontario", "Toronto", "Lac Érié", "Boston", "New York", "ÉTATS-UNIS", "Rivière Missouri",
                            "LOUISIANE", "Fleuve Mississippi"], 

    "Quebec_1800":          ["Baie\nd'Hudson", "Fort\nChurchill", "Fort York", "Fort Severn", "TERRE DE RUPERT", "Fort Albany",
                            "Fort Eastmain", "Fort Rupert", "Fort Moose", "Fort\nCumberland", "Lac\nWinnipeg", "Lac Supérieur", 
                            "PROVINCE\nDE QUÉBEC", "Québec", "Fleuve Saint-Laurent", "ÎLE\nSAINT-\nJEAN", "TERRE-\nNEUVE", 
                            "ÎLE DU\nCAP-\nBRETON", "NOUVEAU-\nBRUNSWICK", "Montréal", "NOUVELLE-\nÉCOSSE", "OCÉAN\nATLANTIQUE",
                            "Lac Michigan", "Lac Huron", "Lac\nOntario", "Lac Érié", "Boston", "New York", "Rivière\nMissouri",
                            "Fleuve\nMississippi", "LOUISIANE"],

    "Quebec_Traite1783":    ["Mer du Labrador", "Baie\nd'Hudson", "TERRE DE RUPERT", "TERRE-\nNEUVE", "PROVINCE\nDE QUÉBEC",
                            "Miquelon", "Saint-Pierre", "Fleuve Saint-Laurent", "ÎLE\nSAINT-\nJEAN", "Québec", "NOUVELLE-\nÉCOSSE",
                            "Montréal", "Lac Supérieur", "Lac Michigan", "Lac Huron", "Lac\nOntario", "Lac Érié", "Boston",
                            "New York", "OCÉAN\nATLANTIQUE", "Rivière Ohio", "Rivière\nMissouri", "Fleuve\nMississippi",
                            "ÉTATS-UNIS", "LOUISIANE", "La Nouvelle-\nOrléans", "Golfe\ndu Mexique", "FLORIDE"],

    "Sahel_Afrique":        ["Algérie", "Mauritanie", "Sénégal", "Mali", "Burkina\nFaso", "Niger", "Nigeria", "Tchad", "Soudan", 
                            "Érythrée", "Éthiopie"],

    "Degrade_Afrique":      ["Le Sahel en Afrique", "Désert du Sahara", "SAHEL", "MAURITANIE", "MALI", "NIGER", "TCHAD", "SOUDAN",
                            "ERYTHREE", "SENEGAL", "GAMBIE", "BURKINA FASO", "Dakar", "Abidjan", "Lomé", "Douala", 
                            "Tropique du Cancer", "Équateur", "OCÉAN ATLANTIQUE", "OCÉAN INDIEN", "Mer Rouge", "Lac Tchad", 
                            "Le Sahel dans le monde"],

}

# Dictionnaire pour stocker les coordonnées des zones à masquer lors des tests
# Note: Si les images d'origine peuvent être agrandies ou tournées,
# ces coordonnées DOIVENT correspondre aux pixels de l'image *originale* exacte (telle qu'elle est testée).
MAP_TEST_BOUNDS = {
    "1775_Quebec_NordUSA": {
        "title_bounds": {"x": 0, "y": 770, "width": 598, "height": 29},
        "scale_bounds": {"x": 10, "y": 700, "width": 140, "height": 60},
        "compass_bounds": {"x": 10, "y": 10, "width": 150, "height": 150},
    },
    "genocide_Monde": {
        "title_bounds": {"x": 0, "y": 0, "width": 543, "height": 160},
        "legend_bounds": {"x": 0, "y": 560, "width": 543, "height": 44},
    },
    "Nouvelle-France1750": {
        "title_bounds": {"x": 100, "y": 350, "width": 450, "height": 120},
        "legend_bounds": {"x": 120, "y": 550, "width": 330, "height": 210},
    },
    "Progress_wehrmacht_lux_May_1940": {
        "title_bounds": {"x": 170, "y": 0, "width": 181, "height": 60},
    },
    "Quebec_1791": {
        "title_bounds": {"x": 0, "y": 345, "width": 602, "height": 30},
        "legend_bounds": {"x": 430, "y": 250, "width": 172, "height": 75},
    },
    "Quebec_1800": {
        "title_bounds": {"x": 0, "y": 390, "width": 602, "height": 27},
        "legend_bounds": {"x": 330, "y": 10, "width": 272, "height": 75},
    },
    "Quebec_Traite1783": {
        "title_bounds": {"x": 0, "y": 450, "width": 521, "height": 31},
        "legend_bounds": {"x": 330, "y": 240, "width": 191, "height": 60},
    },
    "Sahel_Afrique": {
        "title_bounds": {"x": 0, "y": 0, "width": 602, "height": 30},
    },
    "Degrade_Afrique": {
        "title_bounds": {"x": 0, "y": 515, "width": 602, "height": 50},
    },
}
# fmt: on
