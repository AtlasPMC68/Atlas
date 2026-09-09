import cv2
import numpy as np
from PIL import Image as PILImage


def read_image(image_path) -> np.ndarray:
    """Read image and return RGB float64 [0.0, 1.0]. Handles grayscale, RGBA, and RGB."""
    img = PILImage.open(image_path).convert("RGB")
    return np.array(img).astype(np.float64) / 255.0


def bilateral_denoise(img: np.ndarray, sigma_color: float = 0.05, sigma_spatial: float = 1.0) -> np.ndarray:
    img_f32 = img.astype(np.float32)
    result = cv2.bilateralFilter(img_f32, d=-1, sigmaColor=sigma_color, sigmaSpace=sigma_spatial)
    return result.astype(np.float64)


def upscale_lanczos(img: np.ndarray, scale: int = 2) -> np.ndarray:
    """Upscales using Lanczos interpolation. Returns img unchanged if scale == 1."""
    if scale == 1:
        return img
    h, w = img.shape[:2]
    pil_img = PILImage.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    pil_img = pil_img.resize((w * scale, h * scale), PILImage.LANCZOS)
    return np.array(pil_img).astype(np.float64) / 255.0


def prepare_for_ocr(img: np.ndarray) -> np.ndarray:
    """Converts RGB float64 to BGR uint8 for OpenCV/PIL consumption."""
    if img.dtype != np.uint8:
        img = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    return img[:, :, ::-1]
