import os
import easyocr
import cv2
import logging

LANGUAGE__CODES_HASHMAP = {
    "Abaza": "abq", "Adyghe": "ady", "Afrikaans": "af", "Angika": "ang", "Arabic": "ar", "Assamese": "as",
    "Avar": "ava", "Azerbaijani": "az", "Belarusian": "be", "Bulgarian": "bg", "Bihari": "bh", "Bhojpuri": "bho",
    "Bengali": "bn", "Bosnian": "bs", "Simplified Chinese": "ch_sim", "Traditional Chinese": "ch_tra", "Chechen": "che",
    "Czech": "cs", "Welsh": "cy", "Danish": "da", "Dargwa": "dar", "German": "de", "English": "en", "Spanish": "es",
    "Estonian": "et", "Persian (Farsi)": "fa", "French": "fr", "Irish": "ga", "Goan Konkani": "gom", "Hindi": "hi",
    "Croatian": "hr", "Hungarian": "hu", "Indonesian": "id", "Ingush": "inh", "Icelandic": "is", "Italian": "it",
    "Japanese": "ja", "Kabardian": "kbd", "Kannada": "kn", "Korean": "ko", "Kurdish": "ku", "Latin": "la",
    "Lak": "lbe", "Lezghian": "lez", "Lithuanian": "lt", "Latvian": "lv", "Magahi": "mah", "Maithili": "mai",
    "Maori": "mi", "Mongolian": "mn", "Marathi": "mr", "Malay": "ms", "Maltese": "mt", "Nepali": "ne", "Newari": "new",
    "Dutch": "nl", "Norwegian": "no", "Occitan": "oc", "Pali": "pi", "Polish": "pl", "Portuguese": "pt",
    "Romanian": "ro", "Russian": "ru", "Serbian (cyrillic)": "rs_cyrillic", "Serbian (latin)": "rs_latin",
    "Nagpuri": "sck", "Slovak": "sk", "Slovenian": "sl", "Albanian": "sq", "Swedish": "sv", "Swahili": "sw",
    "Tamil": "ta", "Tabassaran": "tab", "Telugu": "te", "Thai": "th", "Tajik": "tjk", "Tagalog": "tl", "Turkish": "tr",
    "Uyghur": "ug", "Ukranian": "uk", "Urdu": "ur", "Uzbek": "uz", "Vietnamese": "vi"
}

LANGUAGE_CODES = [
    "abq", "ady", "af", "ang", "ar", "as", "ava", "az", "be", "bg", "bh", "bho",
    "bn", "bs", "ch_sim", "ch_tra", "che", "cs", "cy", "da", "dar", "de", "en", "es",
    "et", "fa", "fr", "ga", "gom", "hi", "hr", "hu", "id", "inh", "is", "it", "ja",
    "kbd", "kn", "ko", "ku", "la", "lbe", "lez", "lt", "lv", "mah", "mai", "mi", "mn",
    "mr", "ms", "mt", "ne", "new", "nl", "no", "oc", "pi", "pl", "pt", "ro", "ru",
    "rs_cyrillic", "rs_latin", "sck", "sk", "sl", "sq", "sv", "sw", "ta", "tab",
    "te", "th", "tjk", "tl", "tr", "ug", "uk", "ur", "uz", "vi"
]

def check_language_code(langages: list[str]):
    """
    Check if the provided language codes are valid.
    :param langages: List of language codes to check.
    :return: None
    """
    for code in langages:
        if code not in LANGUAGE_CODES:
            raise ValueError(f"Invalid language code: {code}")
              

def read_text_from_image(image_path, languages=['en']):
    """
    Reads text from an image using EasyOCR.
    :param image_path: Path to the image file.
    :param languages: List of language codes to use for text extraction.
    :return: None
    """

    # Variables checking
    try :
        check_language_code(languages)

    except ValueError as e:
        logger.error( "Error trying to read text from image: " + str(e))
    
    # Initializations
    logger = logging.getLogger(__name__)
    reader = easyocr.Reader(['en', 'de'], gpu=False) # GPU - important performance-wise - constraint too
    #supported_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp', '.ppm', '.pgm', '.pbm') # Others possible with extension conversions

    logger.info(f'Currently readin text in : {image_path} with languages: {languages}')

    # Image preprocessing : shading,
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # This part is a problem when maps are already contrasted
    #gray = cv2.equalizeHist(gray)
    #_, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Old tesseract code :
    #image = image.convert("L")  # Conversion en niveaux de gris
    #enhancer = ImageEnhance.Contrast(image)  # Création d’un enhanceur de contraste
    #image = enhancer.enhance(2.0)  # Augmentation du contraste (2.0 = facteur d’amélioration)
    #image = image.point(lambda x: 0 if x < 140 else 255, '1')     # Binarisation : pixels < 140 -> noir, >= 140 -> blanc

    # Image analysis
    results = reader.readtext(gray)

    # Results
    for bbox, text, conf in results:
        logger.info(f"Detected: '{text}'      confidence {conf:.2f}       coords: {bbox}")

    if not results:
        logger.warning(f"No text detected in image: {image_path}")
        return None
    else:
        return results