import numpy as np
import skimage


def read_image(image_path) -> np.ndarray:
    """Read an image file and normalize it to a 3-channel RGB float array."""
    img = skimage.io.imread(image_path)
    if img is None:
        raise IOError(f"Could not read image for given path: {image_path}")

    img = skimage.util.img_as_float(img)

    if img.ndim == 2:
        img = skimage.color.gray2rgb(img)

    elif img.ndim == 3:
        channels = img.shape[2]

        if channels == 4:
            alpha = img[:, :, 3:4]
            rgb = img[:, :, :3]
            white_bg = np.ones_like(rgb)
            img = (rgb * alpha) + (white_bg * (1 - alpha))

        elif channels > 4:
            img = img[:, :, :3]

    return img


def bilateral_denoise(
    img: np.ndarray, sigma_color: float = 0.05, sigma_spatial: float = 1.0
) -> np.ndarray:
    """Apply bilateral denoising while preserving text edges for OCR."""
    return skimage.restoration.denoise_bilateral(
        img, sigma_color=sigma_color, sigma_spatial=sigma_spatial, channel_axis=-1
    )


def upscale_for_ocr(img: np.ndarray, min_dimension: int = 2000) -> np.ndarray:
    """Upscale the image by 2x only when its largest side is below min_dimension."""
    h, w = img.shape[:2]
    if max(h, w) >= min_dimension:
        return img
    return skimage.transform.rescale(
        img, 2.0, channel_axis=-1, anti_aliasing=True, preserve_range=True
    )


def enhance_contrast_and_sharpen(img: np.ndarray, intensity: float = 3.0) -> np.ndarray:
    """
    Apply non-destructive contrast enhancement via LAB-space CLAHE
    followed by a gentle unsharp mask. Preserves color information.
    """
    intensity = max(1.0, min(10.0, float(intensity)))

    img_uint8 = skimage.util.img_as_ubyte(np.clip(img, 0.0, 1.0))
    lab = skimage.color.rgb2lab(img_uint8)

    l_channel = lab[:, :, 0]
    l_norm = l_channel / 100.0
    clip_limit = 0.005 + intensity * 0.003
    l_enhanced = skimage.exposure.equalize_adapthist(
        l_norm, kernel_size=None, clip_limit=clip_limit
    )
    lab[:, :, 0] = l_enhanced * 100.0

    enhanced_rgb = skimage.color.lab2rgb(lab)

    amount = 0.1 * intensity
    sharpened = skimage.filters.unsharp_mask(
        enhanced_rgb, radius=0.8, amount=amount, channel_axis=-1
    )

    return np.clip(sharpened, 0.0, 1.0)
