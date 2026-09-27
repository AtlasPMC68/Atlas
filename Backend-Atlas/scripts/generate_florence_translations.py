# docker compose run --rm florence-worker python /app/scripts/generate_florence_translations.py
import json
import logging
import os

from PIL import Image, ImageDraw, ImageFont

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import from backend
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ocr", "florence"))
)

from app.utils.map_dictionary_data import MAP_DICTIONARY_CATEGORIZED
from ocr.florence.inference import (
    get_runtime_config,
    load_model_and_processor,
    run_inference,
)

OCR_TASK = "<OCR_WITH_REGION>"


def generate_text_image(text: str, font_path: str = None) -> str:
    """Generate a realistic old-map style image containing the specified text and save to temp file."""
    temp_img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(temp_img)

    try:
        import urllib.request

        font_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "font.ttf"))
        if not os.path.exists(font_file):
            logger.info("Downloading EB Garamond font for realistic map text...")
            urllib.request.urlretrieve(
                "https://github.com/googlefonts/ebgaramond/raw/master/fonts/ttf/EBGaramond-MediumItalic.ttf",
                font_file,
            )

        font = ImageFont.truetype(font_file, 48)
    except Exception as e:
        logger.warning(f"Failed to load custom font: {e}")
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    padding = 30
    img_w = text_w + padding * 2
    img_h = text_h + padding * 2

    # Old map background color (sepia/parchment)
    img = Image.new("RGB", (img_w, img_h), color=(240, 230, 210))
    draw = ImageDraw.Draw(img)

    # Draw text in faded ink (dark gray/brown)
    draw.text((padding, padding), text, font=font, fill=(50, 40, 30))

    # Apply slight blur and noise to simulate old scanned document
    from PIL import ImageFilter

    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

    import os

    temp_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "temp_word.png"))
    img.save(temp_path)
    return temp_path


def main():
    logger.info("Loading Florence-2 model...")
    config = get_runtime_config()
    model, processor = load_model_and_processor(config)

    unique_words = set()
    for cat, words in MAP_DICTIONARY_CATEGORIZED.items():
        for w in words:
            unique_words.add(w)

    logger.info(f"Found {len(unique_words)} unique words to test.")

    florence_translations = {}

    possible_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "arial.ttf",
    ]
    font_path = None
    for pf in possible_fonts:
        if os.path.exists(pf):
            font_path = pf
            break

    count = 0
    total = len(unique_words)

    for word in unique_words:
        count += 1
        from inference import run_pipeline

        img_path = generate_text_image(word, font_path)

        try:
            # Use the real production pipeline instead of raw inference
            result = run_pipeline(model, processor, img_path, config)

            # run_pipeline returns {"<OCR_WITH_REGION>": [...list of detections...]}
            detections = result.get(OCR_TASK, [])
            extracted_words = [d.get("text", "").strip() for d in detections]

            combined_extraction = " ".join(extracted_words).strip()

            import re

            combined_extraction = re.sub(r"<loc_\d+>", "", combined_extraction).strip()

            if combined_extraction:
                if combined_extraction.lower() != word.lower():
                    logger.info(
                        f"[{count}/{total}] '{word}' -> Florence extracted: '{combined_extraction}'"
                    )
                    florence_translations[combined_extraction.lower()] = word
            else:
                logger.warning(f"[{count}/{total}] No text extracted for '{word}'")

        except Exception as e:
            logger.error(f"Error processing '{word}': {e}")

    out_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "florence_translations_result.json")
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(florence_translations, f, ensure_ascii=False, indent=4)

    logger.info(f"Done! Extracted {len(florence_translations)} mismatches.")
    logger.info(f"Results saved to {out_path}")
    logger.info(
        "Pour appliquer ces traductions, copie les clés/valeurs dans ENGLISH_FLORENCE_TO_FRENCH_TRANSLATIONS dans map_dictionary.py."
    )


if __name__ == "__main__":
    main()
