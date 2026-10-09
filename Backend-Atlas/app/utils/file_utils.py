import os

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def validate_file_extension(file_path: str) -> bool:
    supported_file_ext = (
        ".jpg",
        ".jpeg",
        ".png",
        # TODO: Verify which extensions are supported
    )
    ext = os.path.splitext(file_path)[1].lower()
    return ext in supported_file_ext
