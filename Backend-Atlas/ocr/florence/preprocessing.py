import numpy as np
import skimage


def read_image(image_path) -> np.ndarray:
    """
    Read image and formats to RGB float64 format
    :param image_path: Path to the image
    :return: 3 channels RGB formatted numpy array of the image. Values are floats [0.0, 1.0]
    :raises: IOError
    """
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
    return skimage.restoration.denoise_bilateral(img,
                                                  sigma_color=sigma_color,
                                                  sigma_spatial=sigma_spatial,
                                                  channel_axis=-1)

def clahe_color_amplification(img: np.ndarray, amplification: float = 0.03) -> np.ndarray:


    # Extract L and normalize to [0.0, 1.0] for the CLAHE
    img_lab = skimage.color.rgb2lab(img)
    l_channel = img_lab[:, :, 0] / 100.0

    # Apply CLAHE
    l_enhanced = skimage.exposure.equalize_adapthist(
        l_channel,
        kernel_size=(8, 8),
        clip_limit=amplification
    )

    img_lab[:, :, 0] = l_enhanced * 100.0
    img_rgb = skimage.color.lab2rgb(img_lab)
    return np.clip(img_rgb, 0.0, 1.0)
