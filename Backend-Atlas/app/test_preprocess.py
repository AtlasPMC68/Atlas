import sys
import os
sys.path.append('Backend-Atlas/ocr')
import numpy as np
from PIL import Image
from florence import preprocessing as prep
from florence.inference import manually_preprocess_image

img = manually_preprocess_image('Backend-Atlas/tests/assets/Progress_wehrmacht_lux_May_1940.jpg')
img.save('test_out.jpg')
print("Image saved with size:", img.size, "and extents:", img.getextrema())
