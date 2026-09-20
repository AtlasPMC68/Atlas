import cv2
import numpy as np


def read_image(image_path: str) -> np.ndarray:
    """
    Read an image file from disk and return it as an RGB uint8 NumPy array.
    If the image has a transparent background (alpha channel), it blends the image
    over a solid white background so dark text remains visible.
    """
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError(f"Could not read image for given path: {image_path}")

    # If image has an alpha channel (4 channels: BGRA)
    if len(img.shape) == 3 and img.shape[2] == 4:
        bgr = img[:, :, :3]
        alpha = img[:, :, 3]

        # Create solid white background
        white_bg = np.ones_like(bgr, dtype=np.uint8) * 255

        # Blend using the alpha channel as a mask
        alpha_mask = alpha.astype(np.float32)[:, :, np.newaxis] / 255.0
        blended = (bgr.astype(np.float32) * alpha_mask) + (white_bg.astype(np.float32) * (1.0 - alpha_mask))
        img = blended.astype(np.uint8)
    elif len(img.shape) == 2:
        # Grayscale
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def bilateral_denoise(img: np.ndarray, sigma_color: float = 0.04, sigma_spatial: float = 3.0) -> np.ndarray:
    """
    Apply bilateral denoising while preserving text edges for OCR processing.
    Smooths background textures without blurring fine text details.
    """
    sigma_c = int(sigma_color * 255)
    sigma_s = int(sigma_spatial)
    return cv2.bilateralFilter(img, d=5, sigmaColor=sigma_c, sigmaSpace=sigma_s)


def upscale_for_ocr(img: np.ndarray, min_dimension: int = 1800) -> np.ndarray:
    """
    Upscale image exactly to min_dimension (on its longest side) if it's smaller.
    Enhances readability for small fonts on historical maps without blowing up memory.
    """
    h, w = img.shape[:2]
    scale = min_dimension / max(h, w)
    if scale <= 1.0:
        return img
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def enhance_contrast_and_sharpen(img: np.ndarray, intensity: float = 1.8) -> np.ndarray:
    """
    Apply non-destructive contrast enhancement, Gamma correction, and an unsharp mask.
    The Gamma correction darkens midtones (helping dark text on colored backgrounds pop),
    and a slight LAB saturation boost helps separate text color from background color.
    """
    intensity = max(1.0, min(5.0, float(intensity)))

    # 1. Gamma Correction: Darkens the overall image slightly so dark text becomes much darker
    gamma = 1.2
    img_float = img.astype(np.float32) / 255.0
    img_gamma = np.clip(np.power(img_float, gamma) * 255.0, 0, 255).astype(np.uint8)

    # 2. Convert to LAB color space
    lab = cv2.cvtColor(img_gamma, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    # 3. Boost Saturation (A and B channels) by pulling values away from center (128)
    sat_boost = 1.25  # +25% saturation
    a_channel = np.clip(128 + (a_channel.astype(np.float32) - 128) * sat_boost, 0, 255).astype(np.uint8)
    b_channel = np.clip(128 + (b_channel.astype(np.float32) - 128) * sat_boost, 0, 255).astype(np.uint8)

    # 4. Enhance Lightness (L channel) using CLAHE
    clip_limit = max(1.0, min(intensity, 2.5))
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_channel)

    # 5. Merge back to RGB
    lab_enhanced = cv2.merge((l_enhanced, a_channel, b_channel))
    enhanced_rgb = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2RGB)

    # 6. Unsharp Mask to sharpen text edges
    amount = 0.08 * intensity
    blur = cv2.GaussianBlur(enhanced_rgb, (0, 0), 1.0)

    enhanced_float = enhanced_rgb.astype(np.float32)
    blur_float = blur.astype(np.float32)

    sharpened = enhanced_float + amount * (enhanced_float - blur_float)
    return np.clip(sharpened, 0, 255).astype(np.uint8)
