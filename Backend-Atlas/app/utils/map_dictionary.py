import re
import Levenshtein

# fmt: off
# ruff: noqa
MAP_DICTIONARY = {
    # Hydrologie & Relief (Exhaustif)
    "Océan", "Mer", "Golfe", "Baie", "Détroit", "Lac", "Fleuve", "Rivière", "Ruisseau", "Canal", "Île", "Archipel", "Cap", "Péninsule", "Presqu'île", "Isthme", "Mont", "Montagne", "Massif", "Pic", "Volcan", "Vallée", "Gorge", "Plaine", "Plateau", "Désert", "Oasis", "Forêt", "Jungle", "Nord", "Sud", "Est", "Ouest", "Équateur", "Tropique", "Cancer", "Capricorne", "Méridien", "Bassin", "Canyon", "Falaise", "Lagune", "Marais", "Tourbière", "Toundra", "Taïga", "Glacier", "Fjord",
    
    # Continents & Grandes Régions Mondiales
    "Afrique", "Amérique", "Asie", "Europe", "Océanie", "Antarctique", "Eurasie", "Moyen-Orient", "Proche-Orient", "Extrême-Orient", "Occident", "Orient", "Balkans", "Scandinavie", "Caucase", "Mésopotamie", "Levant", "Maghreb", "Sahel", "Sibérie", "Patagonie", "Amazonie", "Caraïbes", "Polynésie", "Mélanésie", "Micronésie", "Groenland", "Péninsule", "Ibérique", "Arabique", "Anatolie", "Mandchourie", "Tibet",

    # Océans & Mers (Exhaustif)
    "Atlantique", "Pacifique", "Indien", "Arctique", "Méditerranée", "Noire", "Rouge", "Morte", "Caspienne", "Aral", "Baltique", "Manche", "Adriatique", "Égée", "Ionienne", "Tyrrhénienne", "Béring", "Sargasses", "Chine", "Japon", "Corail", "Tasman", "Nord", "Celtique", "Iroise", "Marmara", "Azov", "Barents", "Kara", "Laptev", "Tchouktches", "Okhotsk", "Arabie", "Oman", "Baffin", "Beaufort", "Labrador", "Sargasses", "Célèbes", "Sulu", "Java", "Bismarck", "Salomon",

    # Canada, Québec & Nouvelle-France (Histoire et Actuel)
    "Canada", "Québec", "Montréal", "Trois-Rivières", "Gaspésie", "Abitibi", "Témiscamingue", "Saguenay", "Lac-Saint-Jean", "Mauricie", "Outaouais", "Laurentides", "Lanaudière", "Montérégie", "Estrie", "Chaudière-Appalaches", "Bas-Saint-Laurent", "Côte-Nord", "Nord-du-Québec", "Nunavik", "Jamésie", "Iles-de-la-Madeleine", "Acadie", "Louisbourg", "Port-Royal", "Tadoussac", "Nouvelle-France", "Nouvelle-Écosse", "Nouveau-Brunswick", "Terre-Neuve", "Labrador", "Île-du-Prince-Édouard", "Ontario", "Haut-Canada", "Bas-Canada", "Manitoba", "Saskatchewan", "Alberta", "Colombie-Britannique", "Yukon", "Nunavut", "Territoires-du-Nord-Ouest", "Terre-de-Rupert", "Plaisance", "Hochelaga", "Stadaconé", "Rupert", "Anticosti",
    
    # Forts historiques, Lieux coloniaux & Explorateurs
    "Fort", "Chambly", "Richelieu", "Saint-Jean", "Frontenac", "Niagara", "Détroit", "Michilimakinac", "Duquesne", "Beauharnois", "Saint-Louis", "De-Chartres", "Orléans", "Rouillé", "Carillon", "Ticonderoga", "William-Henry", "Sainte-Marie", "Oswego", "Louisiane", "Pays-d'en-Haut", "Illinois", "Pontchartrain", "Rupert", "Albany", "Eastmain", "Severn", "Cumberland", "Saint-Pierre", "Cartier", "Champlain", "Frontenac", "Montcalm", "Wolfe", "Laval", "Maisonneuve", "Mance", "Talon", "La-Salle", "Jolliet", "Marquette", "Vérendrye", "Radisson", "Groseilliers", "Bourgchemin", "Sorel", "Lévis", "Vaudreuil",
    
    # Rivières et Lacs (Monde, Québec, Canada, USA)
    "Lac Huron", "Lac Supérieur", "Lac Michigan", "Lac Érié", "Lac Ontario", "Lac Champlain", "Lac Mistassini", "Lac Winnipeg", "Lac Athabasca", "Lac Victoria", "Lac Tchad", "Lac Tanganyika", "Lac Malawi", "Lac Baïkal", "Lac Léman", "Saint-Laurent", "Outaouais", "Richelieu", "Chaudière", "Saint-Maurice", "Saguenay", "Manicouagan", "Koksoak", "La-Grande", "Nottaway", "Harricana", "Mistassini", "Champlain", "Supérieur", "Huron", "Michigan", "Érié", "Ontario", "Winnipeg", "Athabasca", "Grand-Lac-de-l'Ours", "Grand-Lac-des-Esclaves", "Mississippi", "Missouri", "Ohio", "Kennebec", "Hudson", "Nil", "Amazone", "Gange", "Yangtsé", "Mékong", "Danube", "Rhin", "Volga", "Euphrate", "Tigre", "Tamise", "Seine", "Loire", "Garonne", "Rhône", "Elbe", "Oder", "Vistule", "Dniepr", "Don", "Oural", "Ob", "Ienisseï", "Léna", "Amour", "Brahmapoutre", "Indus", "Colorado", "Columbia", "Mackenzie", "Yukon", "Rio-Grande", "Orénoque", "Paraná", "Congo", "Niger", "Zambèze", "Orange", "Victoria", "Tchad", "Tanganyika", "Malawi", "Baïkal", "Léman",
    
    # Peuples Autochtones & Civilisations Précolombiennes
    "Autochtones", "Amérindiens", "Inuits", "Premières-Nations", "Métis", "Algonquins", "Iroquois", "Hurons", "Wendats", "Mohawks", "Abénaquis", "Cris", "Innus", "Montagnais", "Attikameks", "Micmacs", "Malécites", "Naskapis", "Béothuks", "Sioux", "Comanches", "Apaches", "Navajos", "Cherokees", "Aztecs", "Aztèques", "Mayas", "Incas", "Olmèques", "Toltèques", "Mapuches", "Guaranis", "Caribes", "Arawaks",
    
    # Pays et Empires - Antiquité
    "Empire", "Romain", "Gaule", "Lutèce", "Rome", "Grèce", "Athènes", "Sparte", "Macédoine", "Égypte", "Alexandrie", "Babylone", "Mésopotamie", "Sumer", "Akkad", "Assyrie", "Perse", "Carthage", "Phénicie", "Celtes", "Maurya", "Han", "Qin", "Nubie", "Koush", "Sassanides",

    # Pays et Empires - Moyen-Âge
    "Francs", "Mérovingiens", "Carolingiens", "Saint-Empire", "Germanique", "Byzance", "Constantinople", "Francie", "Aquitaine", "Bourgogne", "Normandie", "Flandre", "Bretagne", "Angleterre", "Wessex", "Mercie", "Écosse", "Irlande", "Castille", "Aragon", "Al-Andalus", "Omeyyades", "Abbassides", "Fatimides", "États", "Pontificaux", "Pologne", "Hongrie", "Kiev", "Mongol", "Mali", "Songhaï",

    # Pays et Empires - Temps Modernes (Renaissance, Découvertes, Lumières)
    "Nouvelle-France", "Treize-Colonies", "Britannique", "Espagne", "Portugal", "Provinces-Unies", "Pays-Bas", "Royaume-Uni", "Grande-Bretagne", "Autriche", "Habsbourg", "Prusse", "Russie", "Ottoman", "Suède", "Danemark", "Pologne-Lituanie", "Venise", "Gênes", "Bourbon", "Tudor", "Ming", "Qing", "Moghol", "Safavide",

    # Pays et États - Époque Contemporaine (19e, 20e, 21e siècles)
    "Canada", "Québec", "États-Unis", "Mexique", "Brésil", "Argentine", "Colombie", "Chili", "Pérou", "France", "Allemagne", "Italie", "URSS", "Union", "Soviétique", "Yougoslavie", "Tchécoslovaquie", "Autriche-Hongrie", "Chine", "Japon", "Inde", "Australie", "Turquie", "Sénégal", "Tchad", "Cameroun", "Burkina", "Faso", "Éthiopie", "Érythrée", "Somalie", "Kenya", "Tanzanie", "Rwanda", "Congo", "Angola", "Namibie", "Afrique-du-Sud", "Algérie", "Maroc", "Tunisie", "Égypte", "Arabie", "Irak", "Iran", "Syrie", "Israël", "Palestine", "Afghanistan", "Pakistan", "Vietnam", "Cambodge", "Laos", "Thaïlande", "Indonésie", "Philippines", "Corée",
    
    # Pays, Capitales & Géographie Mondiale (Actuel & Récent)
    "États-Unis", "Mexique", "Brésil", "Argentine", "Colombie", "Chili", "Pérou", "Royaume-Uni", "France", "Allemagne", "Espagne", "Italie", "Russie", "Chine", "Japon", "Inde", "Australie", "Sénégal", "Mali", "Tchad", "Cameroun", "Burkina", "Faso", "Éthiopie", "Érythrée", "Somalie", "Kenya", "Tanzanie", "Rwanda", "Congo", "Angola", "Namibie", "Afrique-du-Sud", "Algérie", "Maroc", "Tunisie", "Égypte", "Arabie", "Irak", "Iran", "Turquie", "Syrie", "Israël", "Palestine", "Afghanistan", "Pakistan", "Vietnam", "Cambodge", "Laos", "Thaïlande", "Indonésie", "Philippines", "Paris", "Londres", "Berlin", "Moscou", "Washington", "Tokyo", "Pékin", "Dakar", "Abidjan", "Douala", "Lomé", "Kinshasa", "Alger", "Rabat", "Tunis", "Le-Caire", "Jérusalem", "Damas", "Bagdad", "Téhéran", "Kaboul", "New-Delhi", "Islamabad", "Hanoï", "Bangkok", "Jakarta", "Manille", "Séoul", "Pyongyang", "Ottawa", "Mexico", "Brasilia", "Buenos-Aires", "Bogota", "Lima", "Santiago", "Caracas", "La-Havane", "Pretoria", "Nairobi", "Abuja", "Addis-Abeba",

    # Capitales et Villes Mondiales (Actuel & Récent)
    "Paris", "Londres", "Berlin", "Moscou", "Washington", "Tokyo", "Pékin", "Dakar", "Abidjan", "Douala", "Lomé", "Kinshasa", "Alger", "Rabat", "Tunis", "Le-Caire", "Jérusalem", "Damas", "Bagdad", "Téhéran", "Kaboul", "New-Delhi", "Islamabad", "Hanoï", "Bangkok", "Jakarta", "Manille", "Séoul", "Pyongyang", "Ottawa", "Mexico", "Brasilia", "Buenos-Aires", "Bogota", "Lima", "Santiago", "Caracas", "La-Havane", "Pretoria", "Nairobi", "Abuja", "Addis-Abeba",
    
    # 20e Siècle & Conflits (Guerres Mondiales, Guerre Froide)
    "URSS", "Soviétique", "Yougoslavie", "Tchécoslovaquie", "Prusse", "Bohême", "Wehrmacht", "Alliés", "Axe", "Nazie", "Fasciste", "Goulag", "Holocauste", "Shoah", "Génocide", "Massacre", "Armistice", "Traité", "Versailles", "Yalta", "Potsdam", "OTAN", "Pacte", "Varsovie", "Srebrenica", "Arménie", "Holodomor", "Tranchée", "Verdun", "Somme", "Marne", "Stalingrad", "Normandie", "Pearl-Harbor", "Hiroshima", "Nagasaki", "Rideau-de-fer", "Mur", "Berlin", "Vietnam", "Corée", "Algérie", "Indochine",
    
    # Termes politiques et historiques globaux
    "Royaume", "République", "Principauté", "Duché", "Comté", "Fédération", "Confédération", "État", "Province", "Territoire", "Colonie", "Protectorat", "Mandat", "Dominion", "Guerre", "Bataille", "Paix", "Révolution", "Siège", "Campagne", "Constitution", "Charte", "Acte", "Empire", "Canton", "Gouvernement", "Parlement", "Sénat", "Assemblée", "Couronne", "Régence", "Indépendance", "Sécession", "Annexion",
    
    # Amériques : Treize Colonies, Villes Coloniales, et Conquêtes
    "Treize-Colonies", "Massachusetts", "New-Hampshire", "Rhode-Island", "Connecticut", "New-York", "Pennsylvanie", "New-Jersey", "Delaware", "Maryland", "Virginie", "Caroline-du-Nord", "Caroline-du-Sud", "Géorgie", "Boston", "Philadelphie", "Appalaches", "Baltimore", "La-Nouvelle-Orléans", "Miquelon", "Isle-Royale", "Nouvelle-Espagne", "Nouvelle-Néerlande", "Nouvelle-Suède", "Nouvelle-Angleterre", "Floride", "Texas", "Californie", "Alaska", "Hawaï", "Porto-Rico", "Cuba", "Hispaniola", "Saint-Domingue", "Jamaïque",
    
    # Régions Françaises historiques et géographiques
    "Alsace", "Lorraine", "Bourgogne", "Franche-Comté", "Bretagne", "Normandie", "Picardie", "Flandre", "Artois", "Champagne", "Île-de-France", "Centre", "Val-de-Loire", "Aquitaine", "Poitou", "Charentes", "Limousin", "Auvergne", "Rhône-Alpes", "Provence", "Alpes", "Côte-d'Azur", "Corse", "Languedoc", "Roussillon", "Midi-Pyrénées", "Gascogne", "Béarn", "Navarre", "Savoie", "Dauphiné",
    
    # Modificateurs communs, Directions et Autres
    "Grand", "Grandes", "Petit", "Petites", "Nouveau", "Nouvelle", "Ancien", "Ancienne", "Haut", "Haute", "Bas", "Basse", "Central", "Centrale", "Moyen", "Moyenne", "Septentrional", "Septentrionale", "Méridional", "Méridionale", "Oriental", "Orientale", "Occidental", "Occidentale", "Majeur", "Mineur", "Saint", "Sainte", "Isle", "Mont", "Monts", "Lac", "Lacs", "Rivière", "Rivières", "Île", "Îles", "Cap", "Baie", "Golfe", "Mer", "Océan", "Détroit", "Canal", "Val", "Vallée", "Bassin", "Plaine", "Plateau", "Désert", "Forêt", "Bois", "Parc", "Réserve", "Montagne", "Montagnes", "Massif", "Col", "Pic", "Glacier", "Fjord", "Presqu'île", "Péninsule", "Archipel", "Atoll", "Récif", "Banc", "Haut-fond", "Chenal", "Passe", "Bras", "Embouchure", "Estuaire", "Delta", "Source", "Confluent", "Rapides", "Chute", "Chutes", "Cascade", "Cataracte"
}
# fmt: on

MAP_DICTIONARY_LOWER = {w.lower(): w for w in MAP_DICTIONARY}


def _correct_word(word: str) -> str:
    """Correct a single word using Levenshtein distance against the map dictionary."""
    if len(word) < 4:
        return word

    word_lower = word.lower()

    if word_lower in MAP_DICTIONARY_LOWER:
        dict_word = MAP_DICTIONARY_LOWER[word_lower]
        return dict_word.upper() if word.isupper() else dict_word

    best_match = None
    min_dist = 999

    for dict_word_lower, original_dict_word in MAP_DICTIONARY_LOWER.items():
        if abs(len(word_lower) - len(dict_word_lower)) > 2:
            continue

        dist = Levenshtein.distance(word_lower, dict_word_lower)
        allowed_dist = 1 if len(dict_word_lower) <= 6 else 2

        if dist <= allowed_dist and dist < min_dist:
            min_dist = dist
            best_match = original_dict_word

    if best_match:
        return best_match.upper() if word.isupper() else best_match

    return word


def apply_map_dictionary_correction(text: str) -> str:
    """Apply dictionary-based correction to raw OCR text."""
    text_clean = text.strip()
    text_lower = text_clean.lower()

    hallucinations = {
        "d'hudson": "Lac Huron",
        "of hudson": "Lac Huron",
        "maeondion": "Lac Huron",
        "antard": "Lac Ontario",
        "mar de michigan": "Lac Michigan",
        "port-oceane": "Fort Duquesne",
        "mar": "Lac",
    }

    if text_lower in hallucinations:
        return hallucinations[text_lower]

    if text_lower.startswith("mar de "):
        text_clean = "Lac " + text_clean[7:]

    words = re.split(r"(\W+)", text_clean)
    corrected_words = [_correct_word(w) if w.isalpha() else w for w in words]
    return "".join(corrected_words)
