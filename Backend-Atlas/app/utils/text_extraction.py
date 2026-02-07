import os
import easyocr
import cv2
import copy
import logging
import numpy as np

logger = logging.getLogger(__name__)

def extract_text(image: np.ndarray, languages: list[str], gpu_acc: bool = False) -> tuple[list, np.ndarray]:
    """
    Wrapper method handling the text extraction logic. This is mainly to reduce
    the memory overhead as this method is very much resource intensive, and it is
    possible that multiple of these run in parallel.

    :param image: Numpy image array of bytes.
    :param image_name: Name of the image file.
    :param languages: List of language codes to use for text extraction.
    :param gpu_acc: Whether a GPU is available to accelerate image analysis.
    :return: values, clean_image: Returns a tuple of the text information and the pixel
        array of the image, devoid of text.
    """
    logger.debug("Initiating text extraction")
    extractor = TextExtraction(img=image,lang=languages, gpu_acc=gpu_acc)
    extractor.check_language_code_validity()

    text_info =  extractor.read_text_from_image()
    #TODO : image cleaning, just send a copy for now
    #clean_image = extractor.remove_text_from_image(image, text_info)
    clean_image = copy.deepcopy(image)

    logger.debug("Completed text extraction")
    return text_info, clean_image

class TextExtraction:

    # Static class variables
    LANGUAGE_CODES_HASHMAP = {
        "Abaza": "abq", "Adyghe": "ady", "Afrikaans": "af", "Angika": "ang", "Arabic": "ar", "Assamese": "as",
        "Avar": "ava", "Azerbaijani": "az", "Belarusian": "be", "Bulgarian": "bg", "Bihari": "bh",
        "Bhojpuri": "bho",
        "Bengali": "bn", "Bosnian": "bs", "Simplified Chinese": "ch_sim", "Traditional Chinese": "ch_tra",
        "Chechen": "che",
        "Czech": "cs", "Welsh": "cy", "Danish": "da", "Dargwa": "dar", "German": "de", "English": "en",
        "Spanish": "es",
        "Estonian": "et", "Persian (Farsi)": "fa", "French": "fr", "Irish": "ga", "Goan Konkani": "gom",
        "Hindi": "hi",
        "Croatian": "hr", "Hungarian": "hu", "Indonesian": "id", "Ingush": "inh", "Icelandic": "is",
        "Italian": "it",
        "Japanese": "ja", "Kabardian": "kbd", "Kannada": "kn", "Korean": "ko", "Kurdish": "ku", "Latin": "la",
        "Lak": "lbe", "Lezghian": "lez", "Lithuanian": "lt", "Latvian": "lv", "Magahi": "mah", "Maithili": "mai",
        "Maori": "mi", "Mongolian": "mn", "Marathi": "mr", "Malay": "ms", "Maltese": "mt", "Nepali": "ne",
        "Newari": "new",
        "Dutch": "nl", "Norwegian": "no", "Occitan": "oc", "Pali": "pi", "Polish": "pl", "Portuguese": "pt",
        "Romanian": "ro", "Russian": "ru", "Serbian (cyrillic)": "rs_cyrillic", "Serbian (latin)": "rs_latin",
        "Nagpuri": "sck", "Slovak": "sk", "Slovenian": "sl", "Albanian": "sq", "Swedish": "sv", "Swahili": "sw",
        "Tamil": "ta", "Tabassaran": "tab", "Telugu": "te", "Thai": "th", "Tajik": "tjk", "Tagalog": "tl",
        "Turkish": "tr",
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
    image: np.ndarray

    # Class members
    def __init__(self, img, lang: list[str] = ['en', 'fr'], gpu_acc: bool = False):
        self.image      : np.ndarray    = img
        self.lang       : list[str]     = list(lang)
        self.gpu_acc    : bool          = gpu_acc

    # Class methods
    def read_text_from_image(self, scale_xy: tuple[float, float] = (2.0,2.0)):

        reader = easyocr.Reader(
            lang_list=list(self.lang),
            gpu=self.gpu_acc,
            verbose=False
        )

        shading = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)

        # NOTE: resizing MUST implies scaling the resulting text or the proportion won't match the original image
        upscaling = cv2.resize(shading, None, fx=scale_xy[0], fy=scale_xy[1], interpolation=cv2.INTER_LANCZOS4)

        extracted_text = reader.readtext(upscaling,
                                  text_threshold=0.7,  # Slightly higher threshold
                                  low_text=0.4,  # low res text detection
                                  link_threshold=0.4,  # character linking tolerance
                                  width_ths=0.7,  # character  spacing tolerance
                                  height_ths=0.7)

        scaled_extracted_text = []
        for (coords, text, prob) in extracted_text:
            #  coords : [top_left, top_right, bottom_right, bottom_left]
            rescaled_coords = []
            for [x, y] in coords:
                rescaled_x = int(x / scale_xy[0])
                rescaled_y = int(y / scale_xy[1])
                rescaled_coords.append([rescaled_x, rescaled_y])

            scaled_extracted_text.append((rescaled_coords, text, prob))

        logger.debug(f"Extracted text: \n{extracted_text}")

        return scaled_extracted_text


    def remove_text_from_image(self, text_info: list):

        image_no_text: np.ndarray = copy.deepcopy(self.image)
        return image_no_text

    def draw_bounding_box(self, scaled_extracted_text) -> np.ndarray:

        image_with_boxes: np.ndarray = copy.deepcopy(self.image)

        # Results and drawing bounding boxes
        for bbox, text, conf in scaled_extracted_text:

            # Convert to numpy array for cv2.polylines
            boxes = np.array(image_with_boxes, dtype=np.int32)

            # Draw red bounding box (thickness=2, red color in BGR format)
            cv2.polylines(image_with_boxes, [boxes], isClosed=True, color=(0, 0, 255), thickness=2)

            # Optional: Add text label above the bounding box
            # Get the top-left corner for text placement
            text_x = bbox[0][0]
            text_y = bbox[0][1] - 10 if bbox[0][1] - 10 > 10 else bbox[0][1] + 20

            # Add confidence score to the label
            label = f"{text} ({conf:.2f})"
            cv2.putText(image_with_boxes, label, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        # TODO: tester cette partie dans une tache future
        # Save the image with bounding boxes
        #filename = os.path.basename(image_path)
        #output_path = os.path.join(os.path.dirname(image_path), f"bbox_{filename}")
        #cv2.imwrite(output_path, image_with_boxes)
        #print(f"Saved image with bounding boxes: {output_path}")

        return results

    def check_language_code_validity(self) -> None:
        """
        :raises ValueError: If at least one language code is not supported.
        """
        for code in self.lang:
            if code not in self.LANGUAGE_CODES:
                raise ValueError(f"Invalid language code: {code}")
