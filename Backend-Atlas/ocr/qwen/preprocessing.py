import cv2
import numpy as np
from PIL import Image as PILImage


def read_image(image_path: str) -> np.ndarray:
    """Read an image from image_path and return as an RGB float64 array normalized to [0.0, 1.0]."""
    img = PILImage.open(image_path).convert("RGB")
    return np.array(img).astype(np.float64) / 255.0


def bilateral_denoise(img: np.ndarray, sigma_color: float = 0.05, sigma_spatial: float = 1.0) -> np.ndarray:
    """
    Apply OpenCV bilateral filtering to an RGB float64 image array.
    Converts to float32 for OpenCV processing and returns the denoised image as float64.
    """
    img_f32 = img.astype(np.float32)
    result = cv2.bilateralFilter(img_f32, -1, float(sigma_color), float(sigma_spatial))
    return result.astype(np.float64)


def upscale_lanczos(img: np.ndarray, scale: int = 2) -> np.ndarray:
    """
    Upscale an image array using PIL Lanczos interpolation.
    Returns the image unchanged if scale == 1.
    """
    if scale == 1:
        return img
    h, w = img.shape[:2]
    pil_img = PILImage.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    pil_img = pil_img.resize((w * scale, h * scale), PILImage.Resampling.LANCZOS)
    return np.array(pil_img).astype(np.float64) / 255.0


def prepare_for_ocr(img: np.ndarray) -> np.ndarray:
    """Convert RGB float64 image array to BGR uint8 array format for OpenCV/PIL consumption."""
    if img.dtype != np.uint8:
        img = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    return img[:, :, ::-1]
