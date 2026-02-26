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
    img: np.ndarray,
    sigma: float = 100.0,
    normalize: bool = True,
    assume_linear: bool = False,
) -> np.ndarray:
    """
    Software flat-field correction: estimates illumination background using Gaussian blur.

    Args:
        img: RGB image float [0.0, 1.0]
        sigma: Gaussian blur sigma (pixels). Higher = smoother background estimate
        normalize: Normalize global intensity after correction
        assume_linear: If True, treat input as linear RGB and avoid rgb2lab on linear data

    Returns:
        Corrected RGB float [0.0, 1.0]
    """
    img = np.clip(skimage.util.img_as_float(img), 0.0, 1.0)

    if not assume_linear:
        img_lab = skimage.color.rgb2lab(img)
        l_channel = img_lab[:, :, 0]

        background = skimage.filters.gaussian(l_channel, sigma=sigma, mode="reflect")
        background = background + 1e-6

        l_corrected = l_channel / background
        l_corrected = l_corrected * float(np.mean(background))

        img_lab[:, :, 0] = l_corrected
        corrected = skimage.color.lab2rgb(img_lab)

    else:
        y = 0.2126 * img[:, :, 0] + 0.7152 * img[:, :, 1] + 0.0722 * img[:, :, 2]
        background = skimage.filters.gaussian(y, sigma=sigma, mode="reflect")
        background = background + 1e-6

        y_corrected = y / background
        y_corrected = y_corrected * float(np.mean(background))

        ratio = (y_corrected / (y + 1e-6)).astype(np.float64)
        corrected = img * ratio[:, :, None]

    if normalize:
        m = float(np.max(corrected))
        if m > 1e-8:
            corrected = corrected / m

    return np.clip(corrected, 0.0, 1.0)



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

def srgb_to_linear(img: np.ndarray) -> np.ndarray:
    """
    Convert sRGB (gamma-compressed) to linear RGB.

    Assumes img is float in [0, 1].
    """
    img = np.clip(img, 0.0, 1.0)
    a = 0.055
    threshold = 0.04045
    low = img / 12.92
    high = ((img + a) / (1.0 + a)) ** 2.4
    return np.where(img <= threshold, low, high)


def linear_to_srgb(img: np.ndarray) -> np.ndarray:
    """
    Convert linear RGB to sRGB (gamma-compressed).

    Assumes img is float in [0, 1] (will be clipped).
    """
    img = np.clip(img, 0.0, 1.0)
    a = 0.055
    threshold = 0.0031308
    low = img * 12.92
    high = (1.0 + a) * (img ** (1.0 / 2.4)) - a
    return np.where(img <= threshold, low, high)


def white_balance_gray_world(img: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Gray-world white balance: scale channels so their mean matches.

    img: float RGB in [0,1]
    mask: optional boolean mask, True = valid pixels to use for stats
    """
    img = np.clip(img, 0.0, 1.0)
    if mask is None:
        pixels = img.reshape(-1, 3)
    else:
        pixels = img[mask]

    if pixels.size == 0:
        return img

    means = np.mean(pixels, axis=0)
    target = float(np.mean(means))
    gains = target / (means + 1e-8)

    out = img * gains.reshape(1, 1, 3)
    return np.clip(out, 0.0, 1.0)


def white_balance_percentile_white_patch(
    img: np.ndarray,
    percentile: float = 99.5,
    mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    White-patch WB using per-channel high percentile.

    This is often better for scanned/photographed maps than gray-world.
    """
    img = np.clip(img, 0.0, 1.0)
    if mask is None:
        pixels = img.reshape(-1, 3)
    else:
        pixels = img[mask]

    if pixels.size == 0:
        return img

    p = np.percentile(pixels, percentile, axis=0)
    gains = 1.0 / (p + 1e-8)

    out = img * gains.reshape(1, 1, 3)
    return np.clip(out, 0.0, 1.0)


def percentile_normalize(
    img: np.ndarray,
    p_low: float = 1.0,
    p_high: float = 99.0,
    mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Robust normalization using percentiles (stable vs max()).

    Maps [p_low, p_high] to [0,1].
    """
    img = np.clip(img, 0.0, 1.0)
    if mask is None:
        pixels = img.reshape(-1, 3)
    else:
        pixels = img[mask]

    if pixels.size == 0:
        return img

    lo = np.percentile(pixels, p_low, axis=0)
    hi = np.percentile(pixels, p_high, axis=0)
    denom = (hi - lo) + 1e-8

    out = (img - lo.reshape(1, 1, 3)) / denom.reshape(1, 1, 3)
    return np.clip(out, 0.0, 1.0)


def build_paper_background_mask(
    img_rgb: np.ndarray,
    opaque_mask: np.ndarray,
    paper_threshold_deltaE: float = 10.0,
) -> np.ndarray:
    """
    Estimate "paper/white" background and exclude it from processing.

    Strategy:
      - Compute LAB on RGB
      - Use a reference white LAB = [100,0,0]
      - Mark pixels close to white as background (deltaE <= threshold)
      - Return updated opaque_mask (foreground mask)
    """
    # Convert to LAB for perceptual distance
    lab = skimage.color.rgb2lab(np.clip(img_rgb, 0.0, 1.0))
    white = np.array([[[100.0, 0.0, 0.0]]], dtype=np.float64)
    dE = skimage.color.deltaE_ciede2000(lab, white)

    background = (dE <= paper_threshold_deltaE) & opaque_mask
    foreground = opaque_mask & (~background)
    return foreground


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


def denoise_nl_means_rgb(
    img: np.ndarray,
    h: float = 0.06,
    fast_mode: bool = True,
) -> np.ndarray:
    """
    Non-local means denoising for RGB.

    h: higher => stronger denoise (risk of losing details)
    """
    img = np.clip(img, 0.0, 1.0)
    sigma_est = np.mean(skimage.restoration.estimate_sigma(img, channel_axis=-1))
    return skimage.restoration.denoise_nl_means(
        img,
        h=h * sigma_est,
        fast_mode=fast_mode,
        patch_size=5,
        patch_distance=6,
        channel_axis=-1,
    )

def clahe_l_channel_lab(
    img: np.ndarray,
    clip_limit: float = 0.02,
    kernel_size: Tuple[int, int] = (8, 8),
) -> np.ndarray:
    """
    CLAHE on LAB L channel for the color-extraction preprocessing pipeline.

    Args:
        img: RGB float image in [0,1]
        clip_limit: CLAHE strength (skimage.equalize_adapthist clip_limit)
        kernel_size: CLAHE tile size

    Returns:
        RGB float image in [0,1]
    """
    img = np.clip(img, 0.0, 1.0)
    lab = skimage.color.rgb2lab(img)

    l = lab[:, :, 0] / 100.0
    l2 = skimage.exposure.equalize_adapthist(l, kernel_size=kernel_size, clip_limit=clip_limit)

    lab[:, :, 0] = l2 * 100.0
    out = skimage.color.lab2rgb(lab)
    return np.clip(out, 0.0, 1.0)

# TODO: DENOISING, COLOR NORMALIZATION, TEST EXISTING FUNCTIONS
