import numpy as np
import skimage


def read_image(image_path) -> np.ndarray:
    """Read an image file and normalize it to a 3-channel RGB float array."""
    # OpenCV reads in RGB format
    img = skimage.io.imread(image_path)
    if img is None:
        raise IOError(f'Could not read image for given path: {image_path}')

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


def bilateral_denoise(img: np.ndarray, sigma_color: float = 0.05, sigma_spatial: float = 1.0) -> np.ndarray:
    """Apply bilateral denoising while preserving text edges for OCR."""
    return skimage.restoration.denoise_bilateral(img,
                                                  sigma_color=sigma_color,
                                                  sigma_spatial=sigma_spatial,
                                                  channel_axis=-1)