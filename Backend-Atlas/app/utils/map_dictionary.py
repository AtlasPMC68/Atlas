import difflib
import re

# fmt: off
# ruff: noqa
MAP_IGNORED_WORDS = {"n", "s", "e", "o",".", "km" "kilomètres", "kilometres", "1", "2", "3", "4", "5", "6", "7","8","9", "légende", "échelle"}

MAP_DICTIONARY = {
    # Hydrologie & Relief
    "Océan", "Mer", "Golfe", "Baie", "Détroit", "Lac", "Fleuve", "Rivière", "Ruisseau", "Canal", "Île", "Archipel", "Cap", "Péninsule", "Presqu'île", "Isthme", "Mont", "Montagne", "Massif", "Pic", "Volcan", "Vallée", "Gorge", "Plaine", "Plateau", "Désert", "Oasis", "Forêt", "Jungle", "Nord", "Sud", "Est", "Ouest", "Équateur", "Tropique", "Cancer", "Capricorne", "Méridien",
    
    # Continents & Régions
    "Afrique", "Amérique", "Asie", "Europe", "Océanie", "Antarctique", "Eurasie", "Moyen-Orient", "Proche-Orient", "Extrême-Orient", "Occident", "Orient",

    # Océans & Mers
    "Atlantique", "Pacifique", "Indien", "Arctique", "Méditerranée", "Noire", "Rouge", "Morte", "Caspienne", "Aral", "Baltique", "Manche", "Adriatique", "Égée", "Ionienne", "Tyrrhénienne", "Caraïbes", "Béring", "Sargasses",

    # Canada & Québec (Histoire et Actuel)
    "Canada", "Québec", "Montréal", "Trois-Rivières", "Gaspésie", "Abitibi", "Témiscamingue", "Saguenay", "Lac-Saint-Jean", "Mauricie", "Outaouais", "Laurentides", "Lanaudière", "Montérégie", "Estrie", "Chaudière-Appalaches", "Bas-Saint-Laurent", "Côte-Nord", "Nord-du-Québec", "Nunavik", "Jamésie", "Iles-de-la-Madeleine", "Acadie", "Louisbourg", "Port-Royal", "Tadoussac", "Nouvelle-France", "Nouvelle-Écosse", "Nouveau-Brunswick", "Terre-Neuve", "Labrador", "Île-du-Prince-Édouard", "Ontario", "Haut-Canada", "Bas-Canada", "Manitoba", "Saskatchewan", "Alberta", "Colombie-Britannique", "Yukon", "Nunavut", "Territoires-du-Nord-Ouest", "Terre-de-Rupert",
    
    # Forts historiques & Lieux coloniaux
    "Fort", "Chambly", "Richelieu", "Saint-Jean", "Frontenac", "Niagara", "Détroit", "Michilimakinac", "Duquesne", "Beauharnois", "Saint-Louis", "De-Chartres", "Orléans", "Rouillé", "Carillon", "Ticonderoga", "William-Henry", "Sainte-Marie", "Oswego", "Louisiane", "Pays-d'en-Haut", "Illinois",
    
    # Rivières et Lacs (Québec/Canada)
    "Saint-Laurent", "Outaouais", "Richelieu", "Chaudière", "Saint-Maurice", "Saguenay", "Manicouagan", "Koksoak", "La-Grande", "Rupert", "Eastmain", "Nottaway", "Harricana", "Abitibi", "Témiscamingue", "Mistassini", "Saint-Jean", "Champlain", "Supérieur", "Huron", "Michigan", "Érié", "Ontario", "Winnipeg", "Athabasca", "Grand-Lac-de-l'Ours", "Grand-Lac-des-Esclaves",
    
    # Peuples Autochtones
    "Autochtones", "Amérindiens", "Inuits", "Premières-Nations", "Métis", "Algonquins", "Iroquois", "Hurons", "Wendats", "Mohawks", "Abénaquis", "Cris", "Innus", "Montagnais", "Attikameks", "Micmacs", "Malécites", "Naskapis", "Béothuks",
    
    # Termes politiques et historiques
    "Empire", "Royaume", "République", "Principauté", "Duché", "Comté", "Fédération", "Confédération", "État", "Province", "Territoire", "Colonie", "Protectorat", "Mandat", "Dominion", "Génocide", "Massacre", "Holocauste", "Guerre", "Bataille", "Traité", "Paix", "Armistice", "Révolution", "Siège", "Campagne", "Constitution", "Charte", "Acte",
    
    # Treize Colonies & USA
    "États-Unis", "Treize-Colonies", "Massachusetts", "New-Hampshire", "Rhode-Island", "Connecticut", "New-York", "Pennsylvanie", "New-Jersey", "Delaware", "Maryland", "Virginie", "Caroline-du-Nord", "Caroline-du-Sud", "Géorgie", "Boston", "Philadelphie", "Washington", "Appalaches", "Mississippi", "Missouri", "Ohio",

    # Modificateurs communs
    "Grand", "Grandes", "Petit", "Petites", "Nouveau", "Nouvelle", "Ancien", "Ancienne", "Haut", "Haute", "Bas", "Basse", "Central", "Centrale", "Moyen", "Moyenne", "Septentrional", "Septentrionale", "Méridional", "Méridionale", "Oriental", "Orientale", "Occidental", "Occidentale", "Majeur", "Mineur", "Saint", "Sainte", "Isle",
}
# fmt: on
MAP_DICTIONARY_LOWER = {w.lower(): w for w in MAP_DICTIONARY}


def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _correct_word(word: str) -> str:
    """Correct a single word if it matches closely to a known map term."""
    if len(word) < 4:
        return word

    word_lower = word.lower()

    # Exact match (case-insensitive)
    if word_lower in MAP_DICTIONARY_LOWER:
        dict_word = MAP_DICTIONARY_LOWER[word_lower]
        return dict_word.upper() if word.isupper() else dict_word

    # Priority to 1-letter difference (Levenshtein distance == 1)
    for dict_word_lower, original_dict_word in MAP_DICTIONARY_LOWER.items():
        if abs(len(word_lower) - len(dict_word_lower)) > 1:
            continue
        dist = levenshtein_distance(word_lower, dict_word_lower)
        if dist == 1:
            return original_dict_word.upper() if word.isupper() else original_dict_word

    # Fallback to fuzzy match with cutoff
    matches = difflib.get_close_matches(word_lower, MAP_DICTIONARY_LOWER.keys(), n=1, cutoff=0.8)
    if matches:
        dict_word = MAP_DICTIONARY_LOWER[matches[0]]
        return dict_word.upper() if word.isupper() else dict_word

    return word


def apply_map_dictionary_correction(text: str) -> str:
    """
    Splits text into words and non-words (punctuation, spaces),
    applies the correction to words, and reconstructs the text.
    """
    words = re.split(r"(\W+)", text)
    corrected_words = [_correct_word(w) if w.isalpha() else w for w in words]
    return "".join(corrected_words)
