import numpy as np
import skimage


def read_image(image_path) -> np.ndarray:
    """
    Upscales the image using Lanczos-4 interpolation to preserve text sharpness.
    :param image_path: Path to the image
    :return: 3 channels RGB formatted numpy array of the image. Values are floats [0.0, 1.0]
    :raises: IOError
    """
    # skimage.io.imread returns an image with channels in RGB order by default
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


def scale_image(img: np.ndarray, width: int = 0, height: int = 0) -> np.ndarray:
    """
    Rescales an RGB image to a given width and height. Untested for LAB image formats
    param img: RGB image with each pixel value in a range of [0.0, 1.0]
    param width: width of the new image
    param height: height of the new image
    return: scaled image: image composed of 3 RGB channels, float values between [0.0, 1.0]
    """

    if width < 0 or height < 0:
        raise ValueError(
            f"Target dimensions must be >= 0. Width: {width}, height: {height}."
        )
    if width == 0 or height == 0:
        raise ValueError(
            f"Width and height must be specified for scaling image. Width: {width}, height: {height}."
        )

    output_shape = (height, width)

    rescaled = skimage.transform.resize(
        img,
        output_shape,
        order=4,
        mode="reflect",  # Mimics the surrounding color gradients
        anti_aliasing=True,  # Only used IF the wanted dimensions are smaller than the actual image
        preserve_range=True,  # Keeping as float64
    )

    # Prevent negative values and values over 1 that comes from using float64
    return np.clip(rescaled, 0.0, 1.0, out=rescaled)


def clahe_color_amplification(
    img: np.ndarray, amplification: float = 0.02
) -> np.ndarray:
    """
    Applies CLAHE to a float64 RGB image.
    :param img: RGB float64 image [0.0, 1.0]
    :param amplification: CLAHE amplification factor. 0.01 is very little, 0.05 is a lot

    :return: Amplified RGB float64 image [0.0, 1.0]
    """
    # L channel is needed for the CLAHE contrast amplification
    img_lab = skimage.color.rgb2lab(img)  # L=[0.0, 100.0]
    l_channel = img_lab[:, :, 0] / 100.0  # L=[0.0, 1.0]

    l_enhanced = skimage.exposure.equalize_adapthist(
        l_channel,
        kernel_size=(8, 8),  # Contextual region (x,y region around each pixel)
        clip_limit=amplification,  # Effect amplification (0.01 is little, 0.05 is a lot)
    )

    # Merge the L channel in the original image
    img_lab[:, :, 0] = l_enhanced * 100.0
    img_lab = np.clip(img_lab, 0.0, 1.0)
    return skimage.color.lab2rgb(img_lab)


def gamma_correction(img: np.ndarray, gamma: float = 0.7, amplitude: float = 0.5):
    """
    Apply a `gamma` exponent to the L channel of every pixel. The amplitude is
    a linear parameter that simply blends the result with the existing values

    :param img:RGB image with float values between [0.0, 1.0]
    :param gamma: The power-law exponent. 0.5 < `gamma` < 1 makes it lighter, 1 < `gamma` < 2 makes it darker.
    Keeping this parameter close to 1 prevent it from being too aggressive
    :param amplitude: The % intensity of the effect (0.0 = no effect, 1.0 = pure gamma result)
    :return: Image with corrected gamma. Values in range [0.0, 1.0]
    """
    if gamma < 0.5 or gamma > 2:
        raise ValueError(f"gamma must be between 0.5 and 2.0. Gamma: {gamma}")

    img_lab = skimage.color.rgb2lab(img)  # L=[0.0, 100.0]
    l_channel = img_lab[:, :, 0] / 100.0  # L=[0.0, 1.0]

    l_gamma = np.power(l_channel, gamma)
    l_gamma = (1.0 - amplitude) * l_channel + amplitude * l_gamma
    img_lab[:, :, 0] = l_gamma * 100.0

    img = skimage.color.lab2rgb(img_lab)
    return np.clip(img, 0.0, 1.0)


def lcn_sharpening_skimage(img: np.ndarray, window_size: int = 15):
    """
    Local Contrast Normalization (LCN) using scikit-image. Acts more or less
    like a high-pass filter

    :param img: Input RGB image (float64, range [0.0, 1.0])
    :param window_size: Size of the Gaussian kernel (must be odd)
    :return: LCN enhanced RGB image with values in the [0.1, 1.0] float64 range
    """
    # Convert to LAB and extract L
    img_float = skimage.util.img_as_float(img)
    lab = skimage.color.rgb2lab(img_float)
    l_channel = lab[:, :, 0]  # Range [0, 100]

    # 2. Local Mean Estimation (average adjacent pixel brightness)
    # sigma is arbitrarily `window_size / 6` for equivalent OpenCV behavior
    sigma = window_size / 6.0
    local_mean = skimage.filters.gaussian(l_channel, sigma=sigma, mode="reflect")
    l_subtracted = l_channel - local_mean

    # E[X^2] - (E[X])^2 approach is faster, but your code uses E[(X-mu)^2]
    local_var = skimage.filters.gaussian(l_subtracted**2, sigma=sigma, mode="reflect")
    local_std = np.sqrt(local_var)

    # 4. Normalization (The Scaling Stage)
    # We add a epsilon (1e-5) to prevent division by zero in flat areas
    l_normalized = l_subtracted / (local_std + 1e-5)

    # 5. Range Rescaling
    # LCN results in a zero-centered signal. For LAB, we must map these.
    l_final = skimage.exposure.rescale_intensity(l_normalized, out_range=(0, 100))

    # 6. Reconstruct
    lab[:, :, 0] = l_final
    result_rgb = skimage.color.lab2rgb(lab)

    return np.clip(result_rgb, 0.0, 1.0)


def flat_field_correction(
    img: np.ndarray, sigma: float = 100.0, normalize: bool = True
) -> np.ndarray:
    """
    Software flat-field correction: estimates illumination background using Gaussian blur.

    :param img: RGB image float [0.0, 1.0]
    :param sigma: Gaussian blur sigma (pixels). Higher = more details removed
    :param normalize: Normalize intensity after correction
    :return: Corrected RGB image float [0.0, 1.0]
    """
    # Convert to LAB for luminance processing
    img_lab = skimage.color.rgb2lab(img)
    l_channel = img_lab[:, :, 0]  # Luminance [0, 100]

    # Apply massive Gaussian blur to estimate illumination background
    background = skimage.filters.gaussian(l_channel, sigma=sigma, mode="reflect")

    # Add small epsilon to avoid division by zero (more stable than np.where)
    epsilon = 1e-6
    background = background + epsilon

    # Correct luminance by dividing by background
    l_corrected = l_channel / background

    # Rescale back to [0, 100] range by multiplying by mean background intensity
    mean_bg = np.mean(background)
    l_corrected = l_corrected * mean_bg

    # Reconstruct LAB image
    img_lab[:, :, 0] = l_corrected

    # Convert back to RGB
    corrected_rgb = skimage.color.lab2rgb(img_lab)

    if normalize:
        max_val = np.max(corrected_rgb)
        if np.isfinite(max_val) and max_val > 0:
            corrected_rgb = corrected_rgb / max_val
        corrected_rgb = np.nan_to_num(corrected_rgb, nan=0.0, posinf=1.0, neginf=0.0)

    return np.clip(corrected_rgb, 0.0, 1.0)


def denoise_bilateral(
    img: np.ndarray, sigma_color: float = 0.05, sigma_spatial: float = 2.0
) -> np.ndarray:
    """
    Removes noise while preserving edge sharpness.
    :param img: RGB image float [0.0, 1.0]
    :param sigma_color: Higher values smooth similar colors
    :param sigma_spatial: Higher values smooth over larger distances.
    """
    # channel_axis=-1 because image is RGB (3 channels at the end)
    return skimage.restoration.denoise_bilateral(
        img, sigma_color=sigma_color, sigma_spatial=sigma_spatial, channel_axis=-1
    )


# TODO: DENOISING, COLOR NORMALIZATION, TEST EXISTING FUNCTIONS
