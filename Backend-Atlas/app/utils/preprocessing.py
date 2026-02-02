import cv2
import numpy as np

def read_image(image_path) -> np.ndarray:
    """
    Upscales the image using Lanczos-4 interpolation to preserve text sharpness.
    :param image_path: Path to the image
    :return: RGB formatted numpy array of the image.
    :raises: IOError
    """
    # OpenCV reads in BGR format
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError(f'Could not read image for given path: {image_path}')

    # Unpredictable results appear when images have opacity in them (16bit).
    # Therefore, we blend each pixel with white proportionally to
    # their opacity, then convert to 8-bit format
    if len(img.shape) == 3 and img.shape[2] == 4:

        alpha = img[:, :, 3] / 255.0
        bgr = img[:, :, :3]
        white_bg = np.ones_like(bgr, dtype=np.uint8) * 255  #

        img = (bgr * alpha[:, :, np.newaxis] + white_bg * (1 - alpha[:, :, np.newaxis])).astype(np.uint8)

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img_rgb

def scale_image(img: np.ndarray, width:int=0, height:int=0, scale_x:float=0.0, scale_y:float=0.0) -> np.ndarray:
    """
    Upscales the image using Lanczos-4 interpolation to preserve text sharpness.
    Will ignore scale_x and scale_y if width/height is not zero.
    :param img: RGB formatted image.
    :param scale_x: Horizontal scale factor. Used ONLY if width/height == 0
    :param scale_y: Vertical scale factor. Used ONLY if width/height == 0
    :param width: Width of the wanted image
    :param height: Height of the wanted image
    :return: The upscaled image.
    """

    if img is None:
        raise IOError(f'None given as a parameter in : {__name__}')

    # Cases where we give a predetermined wanted image size
    if width < 0 or height < 0:
        raise ValueError(f"Wanted image width ({width}) and/or height ({height}) must be greater or equal than zero")
    if (width != 0 and height == 0) or (width == 0 and height != 0):
        raise ValueError(f"Both width and height must be declared. width: {width}, height: {height}")

    # Case where we use the multiplicative scale to calculate the resulting image size
    if width == 0 and height == 0:

        if scale_x <= 0 and scale_y <= 0:
            raise ValueError(f"Image scaling must be a positive non-zero float value. scale_x: {scale_x}, scale_y: {scale_y} ")
        if (width == 0 and height == 0) and (scale_x==0 or scale_y==0):
            raise ValueError(f"Scale value must be non-zero if a predetermined size is not given. scale_x: {scale_x}, scale_y: {scale_y} ")

    # Check that both are not given
    if (width != 0 and height != 0) and (scale_x != 0 and scale_y != 0):
        raise ValueError("Cannot set both width and height and scale_x and scale_y")

    # Using multiplicative scaling
    if width == 0 and height == 0:
        f_width = int(img.shape[1] * scale_x)
        f_height = int(img.shape[0] * scale_y)
        return cv2.resize(src=img, dsize=(f_width, f_height), interpolation=cv2.INTER_LANCZOS4)

    else:
        return cv2.resize(src=img, dsize=(width, height), interpolation=cv2.INTER_LANCZOS4)

