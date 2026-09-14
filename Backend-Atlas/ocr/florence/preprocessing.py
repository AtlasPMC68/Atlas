import cv2
import numpy as np


def read_image(image_path) -> np.ndarray:
    """Read an image file and return it as an RGB uint8 array."""
    # Use cv2 to read the image (returns BGR)
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise IOError(f"Could not read image for given path: {image_path}")
    # Florence uses RGB internally via PIL
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def bilateral_denoise(
    img: np.ndarray, sigma_color: float = 0.05, sigma_spatial: float = 1.0
) -> np.ndarray:
    """Apply bilateral denoising while preserving text edges for OCR."""
    # OpenCV bilateral filter takes integers for sigma
    sigma_c = int(sigma_color * 255)
    sigma_s = int(sigma_spatial)
    return cv2.bilateralFilter(img, d=-1, sigmaColor=sigma_c, sigmaSpace=sigma_s)
    return cv2.bilateralFilter(img, d=5, sigmaColor=sigma_c, sigmaSpace=sigma_s)


def upscale_for_ocr(img: np.ndarray, min_dimension: int = 2000) -> np.ndarray:
    """Upscale the image by 2x only when its largest side is below min_dimension."""
    h, w = img.shape[:2]
    if max(h, w) >= min_dimension:
        return img

    # Bicubic interpolation is good for text
    return cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)


def enhance_contrast_and_sharpen(img: np.ndarray, intensity: float = 3.0) -> np.ndarray:
    """
    Apply non-destructive contrast enhancement via LAB-space CLAHE
    followed by a gentle unsharp mask. Preserves color information.
    """
    intensity = max(1.0, min(10.0, float(intensity)))

    # 1. Convert to LAB color space
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    # 2. Apply CLAHE to L channel only
    clip_limit = max(1.0, intensity)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_channel)

    # 3. Merge back and convert to RGB
    lab_enhanced = cv2.merge((l_enhanced, a_channel, b_channel))
    enhanced_rgb = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2RGB)

    # 4. Unsharp mask
    # formula: sharpened = original + amount * (original - blurred)
    amount = 0.1 * intensity
    blur = cv2.GaussianBlur(enhanced_rgb, (0, 0), 1.0)

    # Convert to float for accurate calculation
    enhanced_float = enhanced_rgb.astype(np.float32)
    blur_float = blur.astype(np.float32)

    sharpened = enhanced_float + amount * (enhanced_float - blur_float)
    return np.clip(sharpened, 0, 255).astype(np.uint8)
