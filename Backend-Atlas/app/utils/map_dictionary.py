import re
import Levenshtein

# Le dictionnaire complet du professeur d'histoire, récupéré du commit précédent.
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

    # Modificateurs communs et Autres
    "Grand", "Grandes", "Petit", "Petites", "Nouveau", "Nouvelle", "Ancien", "Ancienne", "Haut", "Haute", "Bas", "Basse", "Central", "Centrale", "Moyen", "Moyenne", "Septentrional", "Septentrionale", "Méridional", "Méridionale", "Oriental", "Orientale", "Occidental", "Occidentale", "Majeur", "Mineur", "Saint", "Sainte", "Isle", "Dakar", "Abidjan", "Lomé", "Douala", "Tchad", "Mali", "Sénégal", "Burkina", "Faso", "Érythrée", "Srebrenica", "Arménie", "Rwanda", "Cambodge", "Namibie", "Holodomor"
}

MAP_DICTIONARY_LOWER = {w.lower(): w for w in MAP_DICTIONARY}

def _correct_word(word: str) -> str:
    """
    Corrige un seul mot de manière intelligente en utilisant la distance de Levenshtein.
    - Évite les modifications trop agressives (difflib 0.8) qui cassaient les mots courts.
    - Seuls les mots >= 4 lettres sont analysés pour la correction floue.
    """
    if len(word) < 4:
        return word

    word_lower = word.lower()

    # Match exact direct
    if word_lower in MAP_DICTIONARY_LOWER:
        dict_word = MAP_DICTIONARY_LOWER[word_lower]
        return dict_word.upper() if word.isupper() else dict_word

    # Tolérance floue très contrôlée (Levenshtein)
    best_match = None
    min_dist = 999
    
    for dict_word_lower, original_dict_word in MAP_DICTIONARY_LOWER.items():
        # Pas de comparaison avec des mots de longueurs trop différentes
        if abs(len(word_lower) - len(dict_word_lower)) > 2:
            continue
            
        dist = Levenshtein.distance(word_lower, dict_word_lower)
        
        # Tolérance adaptative :
        # - Distance de 1 permise pour les mots de 4 à 6 lettres
        # - Distance de 2 permise pour les gros mots (7+ lettres)
        allowed_dist = 1 if len(dict_word_lower) <= 6 else 2
        
        if dist <= allowed_dist and dist < min_dist:
            min_dist = dist
            best_match = original_dict_word

    if best_match:
        return best_match.upper() if word.isupper() else best_match

    return word

def apply_map_dictionary_correction(text: str) -> str:
    """
    Découpe le texte en mots (en gardant la ponctuation intacte),
    applique la correction intelligente sur chaque mot, puis les recolle.
    """
    # \W+ sépare les mots des non-mots (espaces, traits d'union, ponctuation)
    words = re.split(r"(\W+)", text)
    corrected_words = [_correct_word(w) if w.isalpha() else w for w in words]
    return "".join(corrected_words)
