import os


class Config:
    """Central configuration for the AI Expense Tracker application."""

    # Existing database and authentication configuration
    MONGO_URI = os.getenv("MONGO_URI")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

    # Receipt scanner upload limits
    # Keep uploaded receipts below MongoDB's 16 MB document limit.
    RECEIPT_MAX_BYTES = int(
        os.getenv("RECEIPT_MAX_BYTES", str(10 * 1024 * 1024))
    )

    MAX_CONTENT_LENGTH = RECEIPT_MAX_BYTES

    # Supported receipt image and PDF extensions
    RECEIPT_ALLOWED_EXTENSIONS = frozenset(
        extension.strip().lower()
        for extension in os.getenv(
            "RECEIPT_ALLOWED_EXTENSIONS",
            "png,jpg,jpeg,webp,bmp,tif,tiff,pdf",
        ).split(",")
        if extension.strip()
    )

    # Optional OCR configuration
    # Example language values: eng or eng+hin
    RECEIPT_OCR_LANGUAGE = os.getenv(
        "RECEIPT_OCR_LANGUAGE", "eng"
    )

    # Optional Tesseract executable path
    # Leave unset if Tesseract is available on the system PATH.
    TESSERACT_CMD = os.getenv("TESSERACT_CMD") or None