import os

# The latin recognizer reads accents, the default one does not
OCR_DET_MODEL = os.environ.get("OCR_DET_MODEL", "PP-OCRv5_server_det")
OCR_REC_MODEL = os.environ.get("OCR_REC_MODEL", "latin_PP-OCRv5_mobile_rec")
