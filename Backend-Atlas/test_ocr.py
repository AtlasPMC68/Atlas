import urllib.request
import os
from paddleocr import PaddleOCR

img_path = 'sample.jpg'
urllib.request.urlretrieve('https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/release/2.7/doc/imgs_en/img_12.jpg', img_path)

print("Testing without MKLDNN...")
ocr_no_mkldnn = PaddleOCR(use_angle_cls=True, lang='en', enable_mkldnn=False)
res_no_mkldnn = ocr_no_mkldnn.ocr(img_path)
print(f"Result without MKLDNN: {len(res_no_mkldnn[0]) if res_no_mkldnn and res_no_mkldnn[0] else 'Empty'}")
if res_no_mkldnn and res_no_mkldnn[0]:
    print("First detection:", res_no_mkldnn[0][0])
