"""
Receipt OCR service for AI Expense Tracker.

Responsibilities:
- Extract text from receipt images and PDF files.
- Preprocess images to improve OCR results.
- Parse receipt date, total amount, currency, merchant, and line items.
- Generate basic receipt validation insights.

Optional dependencies:
- Pillow
- pytesseract
- Tesseract OCR executable
- PyMuPDF (fitz) or pypdf for PDF processing

This module does not access the database or define Flask routes.
"""

import io
import os
import re
import shutil
from datetime import datetime
from decimal import Decimal, InvalidOperation


ALLOWED_RECEIPT_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp",
    "bmp",
    "tif",
    "tiff",
    "pdf",
}

# Common Windows installation location.
WINDOWS_TESSERACT_PATH = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


# ---------------------------------------------------------------------
# OCR CONFIGURATION
# ---------------------------------------------------------------------

def _configure_tesseract(pytesseract, tesseract_cmd=None):
    """
    Configure the Tesseract executable.

    Priority:
    1. Explicit tesseract_cmd argument.
    2. TESSERACT_CMD environment variable.
    3. Executable available on the system PATH.
    4. Common Windows installation path.

    Raises:
        RuntimeError: If no usable executable can be located.
    """
    executable = (
        tesseract_cmd
        or os.environ.get("TESSERACT_CMD")
    )

    if executable:
        executable = os.path.expandvars(
            os.path.expanduser(executable)
        )

        # Preserve explicit configuration and let pytesseract
        # report a clear error if the supplied path is invalid.
        pytesseract.pytesseract.tesseract_cmd = executable
        return executable

    path_executable = shutil.which("tesseract")

    if path_executable:
        pytesseract.pytesseract.tesseract_cmd = path_executable
        return path_executable

    if (
        os.name == "nt"
        and os.path.isfile(WINDOWS_TESSERACT_PATH)
    ):
        pytesseract.pytesseract.tesseract_cmd = (
            WINDOWS_TESSERACT_PATH
        )
        return WINDOWS_TESSERACT_PATH

    raise RuntimeError(
        "Tesseract OCR engine was not found. Install Tesseract "
        "and ensure it is available on the system PATH, or set "
        "the TESSERACT_CMD environment variable to the full "
        "path of the Tesseract executable."
    )


def _raise_tesseract_error(pytesseract, exc):
    """Convert a missing Tesseract executable into a clear error."""
    error_type = getattr(
        pytesseract.pytesseract,
        "TesseractNotFoundError",
        None,
    )

    if error_type and isinstance(exc, error_type):
        raise RuntimeError(
            "Tesseract OCR engine could not be started. Verify "
            "that Tesseract is installed and accessible, and "
            "check the TESSERACT_CMD environment variable."
        ) from exc

    raise exc


# ---------------------------------------------------------------------
# OCR AND TEXT EXTRACTION
# ---------------------------------------------------------------------

def extract_receipt_text(
    filename,
    content,
    ocr_language=None,
    tesseract_cmd=None,
):
    """
    Extract text from an uploaded receipt image or PDF.

    Args:
        filename: Original uploaded filename.
        content: File contents as bytes.
        ocr_language: Optional Tesseract language, e.g. "eng".
        tesseract_cmd: Optional path to the Tesseract executable.

    Returns:
        Extracted receipt text as a string.

    Raises:
        ValueError: If the file cannot be processed.
        RuntimeError: If a required dependency or OCR engine is missing.
    """
    if not filename:
        raise ValueError("A receipt filename is required.")

    if not isinstance(content, (bytes, bytearray)):
        raise ValueError("Receipt content must be provided as bytes.")

    if not content:
        raise ValueError("The uploaded receipt file is empty.")

    extension = (
        filename.rsplit(".", 1)[-1].lower()
        if "." in filename
        else ""
    )

    if extension not in ALLOWED_RECEIPT_EXTENSIONS:
        raise ValueError("This receipt file type is not supported.")

    content = bytes(content)

    if extension == "pdf":
        return _extract_pdf_text(
            content,
            ocr_language=ocr_language,
            tesseract_cmd=tesseract_cmd,
        )

    return _extract_image_text(
        content,
        ocr_language=ocr_language,
        tesseract_cmd=tesseract_cmd,
    )


def _extract_image_text(
    content,
    ocr_language=None,
    tesseract_cmd=None,
):
    """Extract text from an image using Tesseract OCR."""
    try:
        import pytesseract
        from PIL import Image, ImageOps, ImageFilter
    except ImportError as exc:
        raise RuntimeError(
            "Image OCR is not configured. Install Pillow and "
            "pytesseract, and install the Tesseract OCR engine."
        ) from exc

    _configure_tesseract(pytesseract, tesseract_cmd)

    try:
        with Image.open(io.BytesIO(content)) as source_image:
            image = ImageOps.exif_transpose(source_image)
            image = image.convert("RGB")

        # Basic preprocessing for common receipt photographs.
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)
        image = image.filter(ImageFilter.SHARPEN)

        options = {"config": "--psm 6"}

        if ocr_language:
            options["lang"] = ocr_language

        return (
            pytesseract.image_to_string(image, **options) or ""
        ).strip()

    except Exception as exc:
        _raise_tesseract_error(pytesseract, exc)

        raise ValueError(
            "The image could not be processed. Try a clearer JPG or PNG image."
        ) from exc


def _extract_pdf_text(
    content,
    ocr_language=None,
    tesseract_cmd=None,
):
    """Extract embedded PDF text and OCR scanned pages when possible."""
    text_parts = []

    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None

    if fitz is not None:
        document = None

        try:
            document = fitz.open(
                stream=content,
                filetype="pdf",
            )

            for page in document:
                page_text = page.get_text("text") or ""

                if page_text.strip():
                    text_parts.append(page_text)
                    continue

                # Limit OCR attempts to the first three pages
                # without embedded text.
                if len(text_parts) < 3:
                    try:
                        import pytesseract
                        from PIL import Image

                        _configure_tesseract(
                            pytesseract,
                            tesseract_cmd,
                        )

                        pixmap = page.get_pixmap(
                            matrix=fitz.Matrix(2, 2),
                            alpha=False,
                        )

                        with Image.open(
                            io.BytesIO(pixmap.tobytes("png"))
                        ) as page_image:
                            options = {}

                            if ocr_language:
                                options["lang"] = ocr_language

                            page_ocr_text = (
                                pytesseract.image_to_string(
                                    page_image,
                                    **options,
                                )
                                or ""
                            )

                        text_parts.append(page_ocr_text)

                    except ImportError:
                        # Embedded PDF text may still be available.
                        pass

                    except Exception as exc:
                        if "pytesseract" in locals():
                            _raise_tesseract_error(
                                pytesseract,
                                exc,
                            )

                        # Preserve embedded text if optional OCR
                        # dependencies are unavailable.
                        pass

            return "\n".join(text_parts).strip()

        except RuntimeError:
            raise

        except Exception as exc:
            raise ValueError(
                "The PDF could not be read. Please upload a valid, "
                "unencrypted PDF."
            ) from exc

        finally:
            if document is not None:
                document.close()

    # Fallback for text-based PDFs when PyMuPDF is unavailable.
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF reading is not configured. Install PyMuPDF "
            "(recommended) or pypdf."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(content))

        if reader.is_encrypted:
            raise ValueError(
                "Encrypted PDFs are not supported. Upload an unencrypted PDF."
            )

        for page in reader.pages[:20]:
            text_parts.append(page.extract_text() or "")

        return "\n".join(text_parts).strip()

    except ValueError:
        raise

    except Exception as exc:
        raise ValueError(
            "The PDF could not be read. Please upload a valid PDF."
        ) from exc


# ---------------------------------------------------------------------
# RECEIPT FIELD PARSING
# ---------------------------------------------------------------------

def parse_receipt_date(text):
    """
    Find a recognizable receipt date and return YYYY-MM-DD.

    Supports:
    - YYYY-MM-DD
    - YYYY/MM/DD
    - YYYY.MM.DD
    - DD-MM-YYYY and corresponding slash/dot formats
    - DD Month YYYY, e.g. 14 October 2026
    """
    if not text:
        return None

    patterns = [
        r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b",
        r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b",
    ]

    for pattern_index, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text):
            try:
                if pattern_index == 0:
                    year, month, day = map(int, match.groups())
                else:
                    day, month, year = map(int, match.groups())

                return datetime(
                    year,
                    month,
                    day,
                ).date().isoformat()

            except ValueError:
                continue

    month_names = (
        "January February March April May June "
        "July August September October November December"
    )

    month_pattern = (
        r"\b(\d{1,2})\s+("
        + "|".join(month_names.split())
        + r")\s+(20\d{2})\b"
    )

    match = re.search(
        month_pattern,
        text,
        flags=re.IGNORECASE,
    )

    if match:
        try:
            month = datetime.strptime(
                match.group(2).title(),
                "%B",
            ).month

            return datetime(
                int(match.group(3)),
                month,
                int(match.group(1)),
            ).date().isoformat()

        except ValueError:
            pass

    return None


def parse_receipt_amount(text):
    """
    Extract a likely grand total.

    Total-labelled lines are preferred. If no such line is found,
    the parser falls back to amounts found anywhere in the text.

    This is a heuristic; ambiguous results should be reviewed.
    """
    if not text:
        return None

    amount_pattern = (
        r"(?:₹|Rs\.?|INR\s*)?\s*"
        r"([0-9]{1,7}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?"
        r"|[0-9]+\.[0-9]{1,2})"
    )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    preferred = []

    for line in lines:
        if re.search(
            r"\b(grand\s+total|total\s+amount|amount\s+due|"
            r"net\s+amount|balance\s+due|total)\b",
            line,
            flags=re.IGNORECASE,
        ):
            preferred.extend(
                re.findall(
                    amount_pattern,
                    line,
                    flags=re.IGNORECASE,
                )
            )

    candidates = preferred or re.findall(
        amount_pattern,
        text,
        flags=re.IGNORECASE,
    )

    parsed = []

    for candidate in candidates:
        try:
            value = Decimal(candidate.replace(",", ""))

            if Decimal("0") < value < Decimal("100000000"):
                parsed.append(value)

        except InvalidOperation:
            continue

    if not parsed:
        return None

    return float(max(parsed))


def parse_receipt_currency(text):
    """Identify a currency from common symbols and currency codes."""
    if not text:
        return None

    upper = text.upper()

    if "₹" in text or re.search(r"\b(INR|RS\.?|RUPEES?)\b", upper):
        return "INR"

    if "$" in text or re.search(r"\bUSD\b", upper):
        return "USD"

    if "€" in text or re.search(r"\bEUR\b", upper):
        return "EUR"

    if "£" in text or re.search(r"\bGBP\b", upper):
        return "GBP"

    return None


def parse_receipt_merchant(text, filename=None):
    """
    Guess the merchant from the first few lines of receipt text.

    Falls back to the filename if no likely merchant is identified.
    """
    ignored = re.compile(
        r"(receipt|invoice|tax invoice|bill no|invoice no|date|time|"
        r"cashier|gstin|\bphone\b|\bwww\.|http|\btotal\b|\bamount\b)",
        re.IGNORECASE,
    )

    if text:
        for line in text.splitlines()[:8]:
            clean = re.sub(r"\s+", " ", line).strip(" -|:")

            if (
                len(clean) >= 3
                and not ignored.search(clean)
                and not re.fullmatch(r"[\d\W]+", clean)
            ):
                return clean[:120]

    base = os.path.splitext(
        os.path.basename(filename or "")
    )[0]

    return base[:120] if base else "Unknown merchant"


def parse_receipt_items(text):
    """
    Heuristically identify receipt line items.

    Returns dictionaries containing name, line_total and quantity.
    These estimates depend on OCR quality and receipt layout.
    """
    items = []

    if not text:
        return items

    skip = re.compile(
        r"(subtotal|grand\s+total|total|tax|gst|cgst|sgst|discount|"
        r"cash|change|balance|amount\s+due|invoice|receipt|thank\s+you|"
        r"date|time|phone|address|gstin|payment|card|round\s*off)",
        re.IGNORECASE,
    )

    price_pattern = re.compile(
        r"(?:₹|Rs\.?\s*)?"
        r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)\s*$",
        re.IGNORECASE,
    )

    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip(" \t|-")

        if len(line) < 3 or skip.search(line):
            continue

        match = price_pattern.search(line)

        if not match:
            continue

        name = line[:match.start()].strip(" .:-xX*")

        if len(name) < 2 or re.fullmatch(r"[\d\W]+", name):
            continue

        try:
            price = float(match.group(1).replace(",", ""))
        except ValueError:
            continue

        if 0 < price < 10000000:
            items.append(
                {
                    "name": name[:120],
                    "line_total": round(price, 2),
                    "quantity": None,
                }
            )

        if len(items) >= 100:
            break

    return items


# ---------------------------------------------------------------------
# COMBINED PARSING AND VALIDATION INSIGHTS
# ---------------------------------------------------------------------

def parse_receipt(text, filename=None):
    """
    Parse common receipt fields from extracted OCR text.

    Returns merchant, date, total, currency, items and warnings.
    """
    text = text or ""

    merchant = parse_receipt_merchant(text, filename)
    receipt_date = parse_receipt_date(text)
    total_amount = parse_receipt_amount(text)
    currency = parse_receipt_currency(text)
    items = parse_receipt_items(text)

    warnings = []

    if not text.strip():
        warnings.append(
            "No readable text was detected. Try a clearer receipt image."
        )

    if not receipt_date:
        warnings.append(
            "Receipt date could not be identified."
        )

    if total_amount is None:
        warnings.append(
            "Receipt total could not be identified."
        )

    if not items:
        warnings.append(
            "No line items were confidently identified."
        )

    if not currency:
        warnings.append(
            "Currency could not be identified automatically."
        )

    return {
        "merchant": merchant,
        "receipt_date": receipt_date,
        "total_amount": total_amount,
        "currency": currency,
        "items": items,
        "warnings": warnings,
    }


def make_receipt_insights(parsed):
    """
    Create approximate consistency checks for parsed receipt data.

    OCR may miss items, taxes, discounts or other charges.
    """
    parsed = parsed or {}

    items = parsed.get("items") or []
    amount = parsed.get("total_amount")

    item_sum = round(
        sum(
            float(item.get("line_total") or 0)
            for item in items
        ),
        2,
    )

    matches_receipt = None

    if amount is not None and items:
        try:
            amount_value = float(amount)

            matches_receipt = (
                abs(item_sum - amount_value)
                <= max(1.0, amount_value * 0.05)
            )
        except (TypeError, ValueError):
            matches_receipt = None

    return {
        "item_count": len(items),
        "items_total_estimate": item_sum,
        "receipt_total": amount,
        "items_total_matches_receipt": matches_receipt,
        "review_recommended": bool(parsed.get("warnings")),
    }


def process_receipt(
    filename,
    content,
    ocr_language=None,
    tesseract_cmd=None,
):
    """
    Extract text and parse a receipt in one call.

    This function does not save expenses or write to the database.
    Those responsibilities remain with the application's backend.
    """
    extracted_text = extract_receipt_text(
        filename=filename,
        content=content,
        ocr_language=ocr_language,
        tesseract_cmd=tesseract_cmd,
    )

    parsed = parse_receipt(
        text=extracted_text,
        filename=filename,
    )

    parsed["insights"] = make_receipt_insights(parsed)

    return {
        "extracted_text": extracted_text,
        "parsed": parsed,
    }