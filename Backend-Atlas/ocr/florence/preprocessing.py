import cv2
import numpy as np


def read_image(image_path: str) -> np.ndarray:
    """
    Read an image file from disk and return it as an RGB uint8 NumPy array.
    Converts from OpenCV default BGR format to RGB format required by Florence and PIL.
    """
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise IOError(f"Could not read image for given path: {image_path}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def bilateral_denoise(img: np.ndarray, sigma_color: float = 0.04, sigma_spatial: float = 3.0) -> np.ndarray:
    """
    Apply bilateral denoising while preserving text edges for OCR processing.
    Smooths background textures without blurring fine text details.
    """
    sigma_c = int(sigma_color * 255)
    sigma_s = int(sigma_spatial)
    return cv2.bilateralFilter(img, d=5, sigmaColor=sigma_c, sigmaSpace=sigma_s)


def upscale_for_ocr(img: np.ndarray, min_dimension: int = 2000) -> np.ndarray:
    """
    Upscale image by 2x using bicubic interpolation when its largest side is below min_dimension.
    Enhances readability for small fonts on historical maps without blowing up memory.
    """
    h, w = img.shape[:2]
    if max(h, w) >= min_dimension:
        return img
    return cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)


def enhance_contrast_and_sharpen(img: np.ndarray, intensity: float = 1.8) -> np.ndarray:
    """
    Apply non-destructive contrast enhancement via LAB-space CLAHE followed by an unsharp mask.
    Converts to LAB color space, enhances L-channel with CLAHE, converts back to RGB,
    and applies a gentle unsharp mask (sharpened = original + amount * (original - blurred))
    to sharpen text edges without amplifying background noise or creating color halos.
    """
    intensity = max(1.0, min(5.0, float(intensity)))

    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    clip_limit = max(1.0, min(intensity, 2.5))
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_channel)

    lab_enhanced = cv2.merge((l_enhanced, a_channel, b_channel))
    enhanced_rgb = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2RGB)

    amount = 0.08 * intensity
    blur = cv2.GaussianBlur(enhanced_rgb, (0, 0), 1.0)

    enhanced_float = enhanced_rgb.astype(np.float32)
    blur_float = blur.astype(np.float32)

    sharpened = enhanced_float + amount * (enhanced_float - blur_float)
    return np.clip(sharpened, 0, 255).astype(np.uint8)
