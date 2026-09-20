import logging
import Levenshtein

logger = logging.getLogger(__name__)

# Liste des mots/termes valides et attendus sur les cartes historiques.
# (Lexique ou "Gazetteer")
VALID_MAP_TERMS = [
    # Toponymes généraux
    "Océan Pacifique",
    "Océan Atlantique",
    "Océan Indien",
    "Océan Arctique",
    "Mer du Labrador",
    "Mer Rouge",
    "Mer Méditerranée",
    "Mer des Caraïbes",
    "Golfe du Mexique",
    "Baie d'Hudson",
    # Noms géographiques spécifiques aux cartes testées
    "Echternach",
    "Labrador",
    "Missouri",
    "HAUT-CANADA",
    "BAS-CANADA",
    "Supérieur",
    "Tadoussac",
    "Isle Royale",
    "Philadelphie",
    "Nouvelle-Orléans",
    "New York",
    "Eastmain",
    "Nemaska",
    "Mistissini",
    "Whapmagoostui",
    "Chisasibi",
    "Wemindji",
    "Waskaganish",
    "Oujé-Bougoumou",
    "Plaisance",
    "Fort Duquesne",
    "Montréal",
    "Québec",
    "Trois-Rivières",
    "Lac Huron",
    "Lac Ontario",
    "Lac Michigan",
    "Lac Érié",
    "Lac Supérieur",
    "Fleuve Saint-Laurent",
    "Fleuve Mississippi",
    "Rivière Missouri",
    "Rivière Ohio",
    "Pays d'en Hauts",
    "Isle St-Jean",
    "Fort St-Pierre",
    "Fort Beauharnois",
    "Fort Michilimakinac",
    "Fort Détroit",
    "Baltimore",
    "Miquelon",
    "Désert du Sahara",
    "Lac Tchad",
    "Sénégal",
    "Burkina Faso",
    "Mali",
    "Dakar",
    "Douala",
    "Érythrée",
    "Abidjan",
    "Canada",
    "Holodomor",
    "Holocauste",
    "Srebrenica",
    "Arménie",
    "Rwanda",
    "Cambodge",
    "Namibie",
]


def correct_text_fuzzy(text: str, max_distance: int = 3) -> str:
    """
    Vérifie si le texte (ou une sous-partie) ressemble fortement à un terme valide.
    """
    best_match = text
    min_dist = 999

    for valid_term in VALID_MAP_TERMS:
        # On compare la distance
        dist = Levenshtein.distance(text.lower(), valid_term.lower())

        # Ajustement : on tolère plus d'erreurs pour les mots très longs
        allowed_dist = min(max_distance, max(1, len(valid_term) // 4))

        if dist <= allowed_dist and dist < min_dist:
            min_dist = dist
            # On remplace par le mot avec la bonne majuscule/orthographe
            best_match = valid_term

    return best_match


def apply_dictionary_corrections(detections: list[dict]) -> list[dict]:
    """
    Applique la correction floue (Fuzzy Matching) sur chaque texte détecté.
    """
    for det in detections:
        original_text = str(det.get("text", "")).strip()
        if not original_text:
            continue

        corrected_text = correct_text_fuzzy(original_text)
        if corrected_text != original_text:
            logger.debug(f"Correction Floue: '{original_text}' corrigé en '{corrected_text}' (dist: {Levenshtein.distance(original_text, corrected_text)})")
            det["text"] = corrected_text

    return detections
