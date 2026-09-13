import numpy as np
import skimage


def read_image(image_path) -> np.ndarray:
    """Read an image file and normalize it to a 3-channel RGB float array."""
    # OpenCV reads in RGB format
    img = skimage.io.imread(image_path)
    if img is None:
        raise IOError(f"Could not read image for given path: {image_path}")

    # Reads the saved image and normalize to float64
    img = skimage.util.img_as_float(img)

    # Greyscale if the array is 2D
    if img.ndim == 2:
        img = skimage.color.gray2rgb(img)

    # Multichannel if the array is 3D
    elif img.ndim == 3:
        channels = img.shape[2]

        # Assume a 4th channel is opacity
        if channels == 4:

            alpha = img[:, :, 3:4]
            rgb = img[:, :, :3]

            white_bg = np.ones_like(rgb)
            img = (rgb * alpha) + (white_bg * (1 - alpha))

        # More than 4 channels is useless and removed
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


def enhance_contrast_and_sharpen(img: np.ndarray, intensity: float = 3.0) -> np.ndarray:
    """
    Apply non-destructive contrast stretching and sharpening.
    Does not use strict binarization to preserve colors.
    """
    intensity = max(1.0, min(10.0, float(intensity)))

    # Échelle douce : intensity=3.0 -> coupe seulement 0.3% des extrêmes (au lieu de 3%)
    # Cela évite de détruire le texte fin qui représente une infime partie de l'image.
    clip_percent = intensity * 0.1
    p_low, p_high = np.percentile(img, (clip_percent, 100 - clip_percent))

    img_rescaled = skimage.exposure.rescale_intensity(img, in_range=(p_low, p_high))

    # Sharpening beaucoup plus léger (amount de 0.2 à 2.0 max au lieu de 5.0)
    # Radius réduit pour éviter les gros halos autour des petites lettres historiques
    amount = intensity * 0.2
    img_sharpened = skimage.filters.unsharp_mask(
        img_rescaled, radius=1.0, amount=amount, channel_axis=-1
    )

    return np.clip(img_sharpened, 0.0, 1.0)
