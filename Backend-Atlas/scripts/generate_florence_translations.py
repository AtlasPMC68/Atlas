import json
import logging
import os
import re
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ocr", "florence"))
)

from app.utils.map_dictionary_data import MAP_DICTIONARY_CATEGORIZED
from inference import run_inference
from ocr.florence.inference import get_runtime_config, load_model_and_processor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
OCR_TASK = "<OCR_WITH_REGION>"


def generate_word_image(word: str) -> Image.Image:
    try:
        font_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "font.ttf"))
        if not os.path.exists(font_file):
            urllib.request.urlretrieve(
                "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf",
                font_file,
            )
        font = ImageFont.truetype(font_file, 48)
    except Exception:
        font = ImageFont.load_default()

    temp_img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(temp_img)
    bbox = draw.textbbox((0, 0), word, font=font)
    w_w = bbox[2] - bbox[0]
    w_h = bbox[3] - bbox[1]

    padding = 40
    img_w = w_w + padding * 2
    img_h = w_h + padding * 2

    img = Image.new("RGB", (img_w, img_h), color=(240, 230, 210))
    draw = ImageDraw.Draw(img)
    draw.text((padding, padding), word, font=font, fill=(50, 40, 30))

    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    return img


def main():
    logger.info("Loading Florence-2 model...")
    config = get_runtime_config()

    model, processor = load_model_and_processor(config)

    unique_words = list({w for words in MAP_DICTIONARY_CATEGORIZED.values() for w in words})
    logger.info(f"Found {len(unique_words)} unique words to test.")

    florence_translations = {}

    for i, word in enumerate(unique_words):
        if i % 5 == 0:
            logger.info(f"Processing word {i}/{len(unique_words)}: '{word}'")

        img = generate_word_image(word)
        try:
            result = run_inference(model, processor, img, OCR_TASK, config)
            ocr_output = result.get(OCR_TASK, {})
            labels = ocr_output.get("labels", []) if isinstance(ocr_output, dict) else []
            raw_text = " ".join(labels)

            if not raw_text:
                continue

            clean_ex = re.sub(r"<loc_\d+>", "", raw_text).strip()

            if clean_ex and clean_ex.lower() != word.lower():
                logger.warning(f"Mismatch! Original: '{word}' -> Florence extracted: '{clean_ex}'")
                florence_translations[clean_ex.lower()] = word

        except Exception as e:
            logger.error(f"Error on {word}: {e}")

    out_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "florence_translations_result.json")
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(florence_translations, f, indent=4, ensure_ascii=False)

    logger.info(f"Done! Found {len(florence_translations)} mistranslations.")
    logger.info(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
