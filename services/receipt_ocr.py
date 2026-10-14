"""
Receipt OCR service for AI Expense Tracker.

Responsibilities:
- Extract text from receipt images and PDF files.
- Preprocess images to improve OCR results.
- Parse receipt date, total amount, currency, merchant, and line items.
- Parse common UPI transaction details.
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

WINDOWS_TESSERACT_PATH = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


# ---------------------------------------------------------------------
# OCR CONFIGURATION
# ---------------------------------------------------------------------

def _configure_tesseract(pytesseract, tesseract_cmd=None):
    """Configure the Tesseract executable."""
    executable = (
        tesseract_cmd
        or os.environ.get("TESSERACT_CMD")
    )

    if executable:
        executable = os.path.expandvars(
            os.path.expanduser(executable)
        )
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
    """Extract text from an uploaded receipt image or PDF."""
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
            "The image could not be processed. "
            "Try a clearer JPG or PNG image."
        ) from exc


def _extract_pdf_text(
    content,
    ocr_language=None,
    tesseract_cmd=None,
):
    """Extract embedded PDF text and OCR scanned pages when possible."""
    text_parts = []

    try:
        import fitz
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
                    pass

                except Exception as exc:
                    if "pytesseract" in locals():
                        _raise_tesseract_error(
                            pytesseract,
                            exc,
                        )

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
                "Encrypted PDFs are not supported. "
                "Upload an unencrypted PDF."
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
    """Find a recognizable date and return YYYY-MM-DD."""
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
    """Extract a likely grand total from receipt text."""
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

    return float(max(parsed)) if parsed else None


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
    """Guess the merchant from receipt text or its filename."""
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
    """Heuristically identify receipt line items."""
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
# UPI TRANSACTION PARSING
# ---------------------------------------------------------------------

def parse_upi_transaction(text, filename=None):
    """
    Parse common UPI transaction text.

    Returns a dictionary compatible with app.py, or None if the text
    does not contain convincing evidence of a UPI/payment transaction.

    This is heuristic OCR parsing, not bank-side transaction verification.
    """
    text = text or ""

    if not text.strip():
        return None

    upi_evidence = re.search(
        r"\b(UPI|VPA|UTR|RRN|Google Pay|GPay|PhonePe|Paytm|BHIM|"
        r"Amazon Pay|WhatsApp Pay|CRED)\b",
        text,
        re.IGNORECASE,
    )

    payment_evidence = re.search(
        r"\b(money sent|money received|paid to|received from|"
        r"payment successful|transaction successful|"
        r"transaction ID|UPI ID|debited|credited)\b",
        text,
        re.IGNORECASE,
    )

    if not upi_evidence and not payment_evidence:
        return None

    warnings = []

    # Identify the payment application.
    platform = None
    platform_patterns = [
        (r"\b(?:Google\s*Pay|GPay|G\s*Pay)\b", "Google Pay"),
        (r"\bPhonePe\b", "PhonePe"),
        (r"\bPaytm\b", "Paytm"),
        (r"\bBHIM\b", "BHIM"),
        (r"\bAmazon\s*Pay\b", "Amazon Pay"),
        (r"\bWhatsApp\s*Pay\b", "WhatsApp Pay"),
        (r"\bCRED\b", "CRED"),
    ]

    for pattern, name in platform_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            platform = name
            break

    if platform is None and re.search(r"\bUPI\b", text, re.IGNORECASE):
        platform = "UPI"

    # Determine whether money was sent or received.
    sent_pattern = (
        r"\b(money sent|you paid|paid to|sent to|"
        r"payment sent|debited|successfully paid)\b"
    )
    received_pattern = (
        r"\b(money received|you received|received from|"
        r"payment received|credited)\b"
    )

    money_sent = bool(
        re.search(sent_pattern, text, re.IGNORECASE)
    )
    money_received = bool(
        re.search(received_pattern, text, re.IGNORECASE)
    )

    if money_sent and not money_received:
        transaction_type = "money_sent"
    elif money_received and not money_sent:
        transaction_type = "money_received"
    else:
        transaction_type = None

    # Only mark success when an explicit success phrase is present.
    failed_payment = bool(re.search(
        r"\b(failed|failure|declined|cancelled|canceled|"
        r"unsuccessful|reversed)\b",
        text,
        re.IGNORECASE,
    ))

    pending_payment = bool(re.search(
        r"\b(pending|processing|in progress)\b",
        text,
        re.IGNORECASE,
    ))

    successful_payment = bool(re.search(
        r"\b(payment successful|transaction successful|"
        r"successfully paid|successfully sent|"
        r"payment completed|transaction completed|"
        r"completed successfully|paid successfully)\b",
        text,
        re.IGNORECASE,
    ))

    if failed_payment:
        payment_status = "failed"
    elif pending_payment:
        payment_status = "pending"
    elif successful_payment:
        payment_status = "success"
    else:
        payment_status = "unknown"

    # A conservative self-transfer warning.
    possible_self_transfer = bool(re.search(
        r"\b(self transfer|self-transfer|own account|"
        r"transfer to self|transferred to own account)\b",
        text,
        re.IGNORECASE,
    ))

    # Extract counterparty from labelled fields or common phrases.
    counterparty = None

    counterparty_patterns = [
        r"\bpaid\s+to\s*[:\-]?\s*([^\r\n]+)",
        r"\bsent\s+to\s*[:\-]?\s*([^\r\n]+)",
        r"\breceived\s+from\s*[:\-]?\s*([^\r\n]+)",
        r"\bcredited\s+by\s*[:\-]?\s*([^\r\n]+)",
        r"\b(?:recipient|merchant|counterparty)\s*[:\-]\s*([^\r\n]+)",
        r"^\s*(?:to|from)\s*[:\-]\s*([^\r\n]+)",
    ]

    # Stop at common metadata labels that may follow the name.
    trailing_metadata = re.compile(
        r"\s+(?:UPI\s*ID|VPA|transaction\s*(?:ID|reference)|"
        r"UTR|RRN|date|time|amount|status)\b.*$",
        re.IGNORECASE,
    )

    for pattern in counterparty_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)

        if not match:
            continue

        candidate = re.sub(
            r"\s+",
            " ",
            match.group(1),
        ).strip(" \t:|,-")

        candidate = trailing_metadata.sub("", candidate).strip(
            " \t:|,-"
        )

        if (
            candidate
            and len(candidate) <= 120
            and not re.fullmatch(r"[\d\W]+", candidate)
        ):
            counterparty = candidate
            break

    # Extract amount from explicitly currency-marked or labelled values.
    amount = None
    amount_patterns = [
        r"(?:₹|Rs\.?|INR)\s*"
        r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"\bamount\b\s*[:\-]?\s*"
        r"(?:₹|Rs\.?|INR)?\s*"
        r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    ]

    amount_candidates = []

    for pattern in amount_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                value = Decimal(match.group(1).replace(",", ""))

                if Decimal("0") < value < Decimal("100000000"):
                    amount_candidates.append(value)

            except (InvalidOperation, ValueError):
                continue

    if amount_candidates:
        amount = float(max(amount_candidates))

    # Reuse the existing receipt date parser.
    transaction_date = parse_receipt_date(text)

    # Recognize a clock time when one is present.
    transaction_time = None
    time_match = re.search(
        r"\b(0?[1-9]|1[0-2]|[01]?\d|2[0-3]):([0-5]\d)"
        r"(?::([0-5]\d))?\s*(AM|PM)?\b",
        text,
        re.IGNORECASE,
    )

    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        second = int(time_match.group(3) or 0)
        meridiem = (time_match.group(4) or "").upper()

        if meridiem:
            if not 1 <= hour <= 12:
                time_match = None
            else:
                hour %= 12
                if meridiem == "PM":
                    hour += 12

        if time_match:
            transaction_time = (
                f"{hour:02d}:{minute:02d}:{second:02d}"
            )

    # Extract a reference only from an explicitly labelled field.
    transaction_reference = None

    reference_pattern = (
        r"\b(?:UPI\s*)?(?:transaction\s*(?:ID|reference|ref|number|no\.?)|"
        r"reference\s*(?:ID|number|no\.?|code)?|"
        r"ref\s*(?:ID|number|no\.?)?|UTR|RRN)\b"
        r"\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/\-]{5,})"
    )

    reference_match = re.search(
        reference_pattern,
        text,
        re.IGNORECASE,
    )

    if reference_match:
        candidate = reference_match.group(1).strip(" /-")

        if not re.fullmatch(r"\d{4}", candidate):
            transaction_reference = candidate

    currency = parse_receipt_currency(text)

    if currency is None and re.search(r"\bUPI\b", text, re.IGNORECASE):
        currency = "INR"

    # Warnings help the UI request a manual review.
    if not platform:
        warnings.append("Payment platform could not be identified.")

    if not counterparty:
        warnings.append("Transaction counterparty could not be identified.")

    if amount is None:
        warnings.append("Transaction amount could not be identified.")

    if not transaction_date:
        warnings.append("Transaction date could not be identified.")

    if not transaction_reference:
        warnings.append("Transaction reference could not be identified.")

    if transaction_type is None:
        warnings.append("Transaction direction could not be confirmed.")

    if payment_status == "unknown":
        warnings.append("Payment success could not be confirmed.")

    if possible_self_transfer:
        warnings.append(
            "This may be a transfer between your own accounts. "
            "Review it before saving an expense."
        )

    return {
        "platform": platform,
        "counterparty": counterparty,
        "amount": amount,
        "transaction_date": transaction_date,
        "transaction_time": transaction_time,
        "currency": currency or "INR",
        "transaction_reference": transaction_reference,
        "transaction_type": transaction_type,
        "payment_status": payment_status,
        "possible_self_transfer": possible_self_transfer,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------
# COMBINED PARSING AND VALIDATION INSIGHTS
# ---------------------------------------------------------------------

def parse_receipt(text, filename=None):
    """Parse common receipt fields from extracted OCR text."""
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
        warnings.append("Receipt date could not be identified.")

    if total_amount is None:
        warnings.append("Receipt total could not be identified.")

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
    """Create approximate consistency checks for parsed receipt data."""
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
    """Extract text and parse a receipt in one call."""
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