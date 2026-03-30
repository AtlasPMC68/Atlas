DEFAULT_IMAGE_HEIGHT_DEGREES = 16.0

def get_png_dimensions(content: bytes) -> tuple[int, int] | None:
    if len(content) < 24 or not content.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    width = int.from_bytes(content[16:20], "big")
    height = int.from_bytes(content[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height

def get_jpeg_dimensions(content: bytes) -> tuple[int, int] | None:
    if len(content) < 4 or not content.startswith(b"\xff\xd8"):
        return None

    sof_markers = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF
    }

    i = 2
    n = len(content)
    while i < n:
        if content[i] != 0xFF:
            i += 1
            continue

        while i < n and content[i] == 0xFF:
            i += 1
        if i >= n:
            break

        marker = content[i]
        i += 1

        if marker in (0xD8, 0xD9):
            continue

        if i + 2 > n:
            break
        seg_len = int.from_bytes(content[i:i+2], "big")
        i += 2

        if seg_len < 2 or i + seg_len - 2 > n:
            break

        if marker in sof_markers:
            if seg_len < 7:
                return None
            height = int.from_bytes(content[i+1:i+3], "big")
            width = int.from_bytes(content[i+3:i+5], "big")
            if width <= 0 or height <= 0:
                return None
            return width, height

        i += seg_len - 2

    return None

def get_image_dimensions(content: bytes) -> tuple[int, int] | None:
    return get_png_dimensions(content) or get_jpeg_dimensions(content)

def default_bounds_from_image(content: bytes) -> list[list[float]]:
    dims = get_image_dimensions(content)
    lat_span = DEFAULT_IMAGE_HEIGHT_DEGREES

    if dims:
        width_px, height_px = dims
        lng_span = lat_span * (width_px / height_px)
    else:
        lng_span = lat_span

    half_lat = lat_span / 2
    half_lng = lng_span / 2
    return [[-half_lat, -half_lng], [half_lat, half_lng]]