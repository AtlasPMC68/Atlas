import cv2
import numpy as np


def read_image(image_path: str) -> np.ndarray:
    """Read an image file from disk and return it as an RGB uint8 NumPy array."""
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError(f"Could not read image for given path: {image_path}")
    return to_rgb(img)


def decode_image(content: bytes) -> np.ndarray:
    """Decode an encoded image (PNG, JPEG, ...) and return it as an RGB uint8 NumPy array."""
    img = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError("Could not decode the image content")
    return to_rgb(img)


def to_rgb(img: np.ndarray) -> np.ndarray:
    """
    Convert an OpenCV image (BGR, BGRA or grayscale) to RGB.
    If the image has a transparent background (alpha channel), it blends the image
    over a solid white background so dark text remains visible.
    """
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


def crop_quad(img: np.ndarray, quad: list[float], margin_ratio: float = 0.15) -> np.ndarray | None:
    """
    Cut a text box out of the image and straighten it into an upright rectangle.
    A margin of margin_ratio times the text height is kept around the box, since
    the recognizer drops the edge letters of tight crops.
    """
    pts = np.array(quad, dtype=np.float32).reshape(4, 2)
    tl, tr, br, bl = pts

    width = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2.0
    height = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2.0
    if width < 2 or height < 2:
        return None

    # Grow the box along its own axes so rotated boxes keep their margin
    u = (tr - tl) / max(np.linalg.norm(tr - tl), 1e-6)
    v = (bl - tl) / max(np.linalg.norm(bl - tl), 1e-6)
    m = margin_ratio * min(width, height)
    grown = np.array([tl - m * u - m * v, tr + m * u - m * v, br + m * u + m * v, bl - m * u + m * v], dtype=np.float32)

    out_w = int(round(width + 2 * m))
    out_h = int(round(height + 2 * m))
    dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(grown, dst)
    return cv2.warpPerspective(img, matrix, (out_w, out_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def enhance_contrast(img: np.ndarray) -> np.ndarray:
    """Apply LAB-space CLAHE on the L-channel to bring out faded text."""
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    l_channel = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(l_channel)
    return cv2.cvtColor(cv2.merge((l_channel, a_channel, b_channel)), cv2.COLOR_LAB2RGB)


def binarize(img: np.ndarray) -> np.ndarray:
    """Otsu threshold a text crop, flipped if needed so the text ends up dark on light."""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # The background is the majority of a text crop
    if np.count_nonzero(binary) < binary.size / 2:
        binary = 255 - binary
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
