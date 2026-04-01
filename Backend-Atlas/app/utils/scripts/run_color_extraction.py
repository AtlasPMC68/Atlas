import os

from app.utils.file_utils import validate_file_extension
from app.utils.color_extraction import extract_colors

# Run the script with:
# cd "\Atlas\Backend-Atlas"
# py -m app.utils.scripts.run_color_extraction 

ASSETS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "tests", "assets"
)

def extract_color_from_assets():


    # for filename in os.listdir(ASSETS_DIR):
    #     file_path = os.path.join(ASSETS_DIR, filename)
    #     if os.path.isfile(file_path) and validate_file_extension(file_path):
    #         print(f"Extracting color from {filename}...")
    #         extract_colors(file_path, debug=True)
    file_path = os.path.join(ASSETS_DIR, "Sols_Monde.png")
    extract_colors(file_path, debug=True, imposed_colors=[(208, 208, 208),(240, 240, 208),(208, 80, 48),(240, 208, 48)]) #
    file_path = os.path.join(ASSETS_DIR, "Degrade_Afrique.png")
    extract_colors(file_path, debug=True, imposed_colors=[(237, 137, 141),(229, 105, 109),(180, 86, 97),(238,176,81),(237,134,81),(147,194,97)])
    file_path = os.path.join(ASSETS_DIR, "pluie_Afrique.png")
    extract_colors(file_path, debug=True, imposed_colors=[(255, 204, 68),(230, 248, 200),(152, 218, 180), (101, 181, 175),(69, 133, 168),(80, 116, 162)])
    
extract_color_from_assets()
