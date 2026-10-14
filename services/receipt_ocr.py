"""
Receipt OCR and UPI Transaction Parsing service for AI Expense Tracker.

Responsibilities:
- Extract text from receipt images and PDF files.
- Preprocess images to improve OCR results.
- Parse receipt date, total amount, currency, merchant and line items.
- Recognize PhonePe, Google Pay, Paytm and other UPI screenshots.
- Extract transaction amount, date, time, reference and payment status.
- Classify money sent, money received and possible self-transfers.
- Generate basic validation insights and warnings.

Optional dependencies:
- Pillow
- pytesseract
- Tesseract OCR executable
- PyMuPDF (fitz) or pypdf for PDF processing

This module does not access the database or define Flask routes.
Automatic expense saving must be integrated in the application backend.
"""

import io
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


ALLOWED_RECEIPT_EXTENSIONS = {
    "png", "jpg", "jpeg", "webp", "bmp",
    "tif", "tiff", "pdf",
}

UPI_PLATFORMS = {
    "phonepe": ("phonepe",),
    "google_pay": ("google pay", "googlepay", "gpay"),
    "paytm": ("paytm",),
    "other_upi": ("upi", "bhim"),
}

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


def _configure_tesseract(pytesseract, tesseract_cmd=None):
    """Configure Tesseract when an executable path is supplied."""
    executable = tesseract_cmd or os.environ.get("TESSERACT_CMD")

    if executable:
        pytesseract.pytesseract.tesseract_cmd = executable


def _extract_image_text(
    content,
    ocr_language=None,
    tesseract_cmd=None,
):
    """Extract image text with Tesseract OCR."""
    try:
        import pytesseract
        from PIL import Image, ImageOps, ImageFilter
    except ImportError as exc:
        raise RuntimeError(
            "Image OCR is not configured. Install Pillow, pytesseract "
            "and the Tesseract OCR engine."
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

    except RuntimeError:
        raise
    except Exception as exc:
        raise ValueError(
            "The image could not be processed. Try a clearer JPG or PNG image."
        ) from exc


def _extract_pdf_text(
    content,
    ocr_language=None,
    tesseract_cmd=None,
):
    """Extract embedded PDF text, using OCR for scanned pages if possible."""
    text_parts = []

    try:
        import fitz
    except ImportError:
        fitz = None

    if fitz is not None:
        document = None

        try:
            document = fitz.open(stream=content, filetype="pdf")

            for page in document:
                page_text = page.get_text("text") or ""

                if page_text.strip():
                    text_parts.append(page_text)
                    continue

                if len(text_parts) < 3:
                    try:
                        import pytesseract
                        from PIL import Image

                        _configure_tesseract(
                            pytesseract, tesseract_cmd
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
                                    page_image, **options
                                ) or ""
                            )

                        text_parts.append(page_ocr_text)

                    except ImportError:
                        pass
                    except Exception:
                        pass

            return "\n".join(text_parts).strip()

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
# SHARED DATE AND AMOUNT HELPERS
# ---------------------------------------------------------------------

def _parse_date_value(value):
    """Convert a recognized date string to YYYY-MM-DD."""
    value = re.sub(r"\s+", " ", (value or "").strip())

    patterns = (
        ("%Y-%m-%d", r"\b20\d{2}-\d{1,2}-\d{1,2}\b"),
        ("%Y/%m/%d", r"\b20\d{2}/\d{1,2}/\d{1,2}\b"),
        ("%d-%m-%Y", r"\b\d{1,2}-\d{1,2}-20\d{2}\b"),
        ("%d/%m/%Y", r"\b\d{1,2}/\d{1,2}/20\d{2}\b"),
        ("%d.%m.%Y", r"\b\d{1,2}\.\d{1,2}\.20\d{2}\b"),
        ("%d %B %Y", r"\b\d{1,2}\s+[A-Za-z]+\s+20\d{2}\b"),
        ("%d %b %Y", r"\b\d{1,2}\s+[A-Za-z]{3}\s+20\d{2}\b"),
    )

    for date_format, pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)

        if not match:
            continue

        try:
            return datetime.strptime(
                match.group(0), date_format
            ).date().isoformat()
        except ValueError:
            continue

    return None


def _parse_amount_value(value):
    """Parse an amount string without treating arbitrary digits as money."""
    if value is None:
        return None

    cleaned = str(value).strip()
    cleaned = re.sub(r"(?i)\b(?:INR|RS\.?|RUPEES?)\b", "", cleaned)
    cleaned = cleaned.replace("₹", "").replace(",", "").strip()
    cleaned = re.sub(r"\s+", "", cleaned)

    if not re.fullmatch(r"\d{1,12}(?:\.\d{1,2})?", cleaned):
        return None

    try:
        amount = Decimal(cleaned)

        if Decimal("0") < amount < Decimal("100000000"):
            return float(amount.quantize(Decimal("0.01")))

    except InvalidOperation:
        pass

    return None


# ---------------------------------------------------------------------
# RECEIPT FIELD PARSING
# ---------------------------------------------------------------------

def parse_receipt_date(text):
    """Find a recognizable receipt date and return YYYY-MM-DD."""
    if not text:
        return None

    for line in text.splitlines():
        result = _parse_date_value(line)

        if result:
            return result

    return None


def parse_receipt_amount(text):
    """Extract a likely receipt total; this is a heuristic."""
    if not text:
        return None

    amount_pattern = (
        r"(?:₹|Rs\.?\s*|INR\s*)?"
        r"(\d{1,7}(?:,\d{3})*(?:\.\d{1,2})?|\d+\.\d{1,2})"
    )

    preferred = []

    for line in text.splitlines():
        if re.search(
            r"\b(grand\s+total|total\s+amount|amount\s+due|"
            r"net\s+amount|balance\s+due|total)\b",
            line,
            re.IGNORECASE,
        ):
            preferred.extend(
                re.findall(amount_pattern, line, re.IGNORECASE)
            )

    candidates = preferred or re.findall(
        amount_pattern, text, re.IGNORECASE
    )

    parsed = [
        amount
        for candidate in candidates
        if (amount := _parse_amount_value(candidate)) is not None
    ]

    return max(parsed) if parsed else None


def parse_receipt_currency(text):
    """Identify common receipt currencies."""
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
    """Guess the merchant from receipt text, falling back to filename."""
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

    base = os.path.splitext(os.path.basename(filename or ""))[0]
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
        r"(\d{1,7}(?:,\d{3})*(?:\.\d{1,2})?)\s*$",
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

        price = _parse_amount_value(match.group(1))

        if price is not None:
            items.append({
                "name": name[:120],
                "line_total": price,
                "quantity": None,
            })

        if len(items) >= 100:
            break

    return items


# ---------------------------------------------------------------------
# UPI PLATFORM, STATUS AND TRANSACTION PARSING
# ---------------------------------------------------------------------

def detect_upi_platform(text):
    """Identify a payment app from OCR text when its name is present."""
    normalized = re.sub(r"\s+", " ", (text or "").lower())

    for platform, names in UPI_PLATFORMS.items():
        if any(name in normalized for name in names):
            return platform

    return None


def _find_transaction_status(text):
    """Return a payment status only when a recognizable status is present."""
    normalized = re.sub(r"\s+", " ", (text or "").lower())

    failure_patterns = (
        r"\b(payment failed|transaction failed|failed transaction|"
        r"payment declined|transaction declined|payment unsuccessful)\b",
    )

    pending_patterns = (
        r"\b(payment pending|transaction pending|processing payment|"
        r"awaiting confirmation|in progress)\b",
    )

    success_patterns = (
        r"\b(payment successful|transaction successful|"
        r"successfully paid|payment completed|transaction completed|"
        r"paid successfully|money sent successfully|"
        r"money received successfully)\b",
    )

    if any(re.search(p, normalized) for p in failure_patterns):
        return "failed"

    if any(re.search(p, normalized) for p in pending_patterns):
        return "pending"

    if any(re.search(p, normalized) for p in success_patterns):
        return "success"

    # Some apps display only a standalone "Successful" or "Completed".
    if re.search(r"\b(successful|completed)\b", normalized):
        return "success"

    return "unknown"


def _find_transaction_amount(text):
    """
    Extract an amount from transaction-labelled lines first.

    Avoid selecting UPI IDs, reference numbers, dates or phone numbers
    as the transaction amount whenever possible.
    """
    if not text:
        return None

    amount_pattern = re.compile(
        r"(?:₹\s*|INR\s*|Rs\.?\s*)"
        r"(\d{1,7}(?:,\d{3})*(?:\.\d{1,2})?|\d+\.\d{1,2})",
        re.IGNORECASE,
    )

    labelled_pattern = re.compile(
        r"\b(amount|paid|sent|debited|received|credited|"
        r"you\s+paid|you\s+sent|you\s+received|"
        r"total\s+paid|payment\s+of)\b",
        re.IGNORECASE,
    )

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = []

    # First pass: explicit currency symbol/code on a transaction line.
    for line in lines:
        if not labelled_pattern.search(line):
            continue

        matches = list(amount_pattern.finditer(line))

        for match in matches:
            amount = _parse_amount_value(match.group(1))

            if amount is not None:
                candidates.append((line, amount))

    if candidates:
        # Prefer an amount on a "Paid", "Sent", "Received" or
        # "Debited" line, rather than a reference or account number.
        priority = re.compile(
            r"\b(paid|sent|debited|received|credited|you\s+paid|"
            r"you\s+sent|you\s+received|total\s+paid|payment\s+of)\b",
            re.IGNORECASE,
        )

        prioritized = [
            amount for line, amount in candidates
            if priority.search(line)
        ]

        if prioritized:
            return prioritized[0]

        return candidates[0][1]

    # Second pass: currency symbols without a transaction label.
    for line in lines:
        matches = list(amount_pattern.finditer(line))

        if matches:
            amount = _parse_amount_value(matches[0].group(1))

            if amount is not None:
                return amount

    # Do not guess from arbitrary bare numbers in a UPI screenshot.
    return None


def _find_transaction_datetime(text):
    """Extract transaction date and time where possible."""
    if not text:
        return None, None

    date_value = None
    time_value = None

    for line in text.splitlines():
        if date_value is None:
            date_value = _parse_date_value(line)

        if time_value is None:
            match = re.search(
                r"\b(0?[1-9]|1[0-2]|0?\d|2[0-3]):([0-5]\d)"
                r"(?:\s*:\s*([0-5]\d))?\s*(AM|PM)?\b",
                line,
                re.IGNORECASE,
            )

            if match:
                raw = re.sub(r"\s+", "", match.group(0)).upper()
                raw = raw.replace("AM", " AM").replace("PM", " PM")

                try:
                    formats = ("%I:%M %p", "%I:%M:%S %p",
                               "%H:%M", "%H:%M:%S")

                    for fmt in formats:
                        try:
                            time_value = datetime.strptime(
                                raw.strip(), fmt
                            ).strftime("%H:%M:%S")
                            break
                        except ValueError:
                            continue
                except (TypeError, ValueError):
                    time_value = None

    return date_value, time_value


def _find_transaction_reference(text):
    """Extract a labelled UPI reference or transaction ID."""
    if not text:
        return None

    patterns = (
        r"\b(?:UPI\s+)?(?:transaction\s+ID|txn\s+ID|"
        r"reference\s+(?:number|no\.?|ID)|UTR|RRN)\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9\-]{5,34})\b",
        r"\bUPI\s+Ref(?:erence)?\s*(?:No\.?|ID)?\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9\-]{5,34})\b",
    )

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            reference = match.group(1).strip()

            if not re.fullmatch(r"\d{10,}", reference):
                return reference

    return None


def _find_party(text, direction):
    """
    Extract a likely counterparty from common UPI labels.

    OCR layouts differ across apps, so this is a best-effort guess.
    """
    if not text:
        return None

    if direction == "money_sent":
        labels = (
            r"(?:paid\s+to|sent\s+to|transferred\s+to|"
            r"money\s+sent\s+to|to)\s*[:\-]?\s*(.+)",
        )
    elif direction == "money_received":
        labels = (
            r"(?:received\s+from|money\s+received\s+from|"
            r"paid\s+by|from)\s*[:\-]?\s*(.+)",
        )
    else:
        return None

    stop_words = re.compile(
        r"\b(amount|₹|inr|rs\.?|upi|transaction|reference|"
        r"successful|completed|pending|failed|date|time|"
        r"paid|debited|credited|received|sent|bank|balance)\b",
        re.IGNORECASE,
    )

    for line in text.splitlines():
        clean = re.sub(r"\s+", " ", line).strip(" :-|")

        for label in labels:
            match = re.search(label, clean, re.IGNORECASE)

            if not match:
                continue

            candidate = match.group(1).strip(" :-|")

            # Avoid returning an entire long OCR paragraph.
            candidate = re.split(
                r"\s{2,}|[|]", candidate
            )[0].strip()

            if stop_words.search(candidate):
                candidate = stop_words.split(candidate)[0].strip(" :-|")

            if (
                2 <= len(candidate) <= 100
                and not re.fullmatch(r"[\d\W]+", candidate)
                and "@" not in candidate
            ):
                return candidate

    return None


def _classify_transaction(text):
    """
    Classify transaction direction from explicit words.

    A possible self-transfer is flagged for review when transfer-related
    words are present. OCR alone cannot reliably prove account ownership.
    """
    normalized = re.sub(r"\s+", " ", (text or "").lower())

    self_transfer = bool(re.search(
        r"\b(self\s+transfer|transferred\s+between\s+my\s+accounts|"
        r"own\s+account|between\s+own\s+accounts)\b",
        normalized,
    ))

    if self_transfer:
        return "transfer", True

    received = bool(re.search(
        r"\b(money\s+received|received\s+from|you\s+received|"
        r"credited\s+to|amount\s+credited|payment\s+received|"
        r"credited)\b",
        normalized,
    ))

    sent = bool(re.search(
        r"\b(money\s+sent|you\s+paid|paid\s+to|you\s+sent|"
        r"sent\s+to|debited|amount\s+debited|transferred\s+to|"
        r"payment\s+sent)\b",
        normalized,
    ))

    if received and sent:
        return "unknown", False

    if received:
        return "money_received", False

    if sent:
        return "money_sent", False

    return "unknown", False


def parse_upi_transaction(text, filename=None):
    """
    Parse a UPI payment screenshot.

    Returns a structured dictionary. This function does not save an expense.
    A later backend step must handle user choice, duplicate checks and saving.
    """
    text = text or ""

    platform = detect_upi_platform(text)
    status = _find_transaction_status(text)
    amount = _find_transaction_amount(text)
    transaction_date, transaction_time = _find_transaction_datetime(text)

    direction, possible_self_transfer = _classify_transaction(text)

    party = _find_party(text, direction)
    reference = _find_transaction_reference(text)

    warnings = []

    if not text.strip():
        warnings.append("No readable text was detected.")

    if not platform:
        warnings.append(
            "Payment app could not be identified. The screenshot may still "
            "contain a readable UPI transaction."
        )

    if amount is None:
        warnings.append(
            "Transaction amount could not be identified confidently."
        )

    if status == "unknown":
        warnings.append(
            "Payment status could not be confirmed. Verify the transaction "
            "before saving it as a completed expense."
        )
    elif status == "failed":
        warnings.append(
            "This transaction appears to have failed. Do not save it as a "
            "completed payment without user confirmation."
        )
    elif status == "pending":
        warnings.append(
            "This transaction appears pending. Verify its final status."
        )

    if direction == "unknown":
        warnings.append(
            "Transaction direction could not be identified confidently."
        )

    if not transaction_date:
        warnings.append("Transaction date could not be identified.")

    if not reference:
        warnings.append(
            "No transaction reference was identified. Duplicate checking "
            "may need amount, date and other available details."
        )

    if possible_self_transfer:
        warnings.append(
            "This may be a transfer between the user's own accounts. "
            "Confirm before including it in spending totals."
        )

    if not party:
        warnings.append(
            "The sender or receiver could not be identified confidently."
        )

    # Only a possible expense, not an instruction to auto-save.
    # The user must be able to choose to record any transaction as an expense.
    return {
        "transaction_type": direction,
        "platform": platform,
        "amount": amount,
        "currency": parse_receipt_currency(text) or (
            "INR" if "₹" in text or re.search(
                r"\b(INR|Rs\.?|UPI)\b", text, re.IGNORECASE
            ) else None
        ),
        "transaction_date": transaction_date,
        "transaction_time": transaction_time,
        "counterparty": party,
        "transaction_reference": reference,
        "payment_status": status,
        "possible_self_transfer": possible_self_transfer,
        "expense_candidate": (
            amount is not None
            and status == "success"
            and direction == "money_sent"
            and not possible_self_transfer
        ),
        "user_can_add_as_expense": amount is not None,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------
# COMBINED PARSING AND VALIDATION INSIGHTS
# ---------------------------------------------------------------------

def parse_receipt(text, filename=None):
    """
    Parse receipt fields and attach UPI details when a transaction
    screenshot is detected.

    Existing receipt fields remain available to existing callers.
    """
    text = text or ""

    upi = parse_upi_transaction(text, filename=filename)

    # Prefer the dedicated UPI amount parser when a transaction screenshot
    # has recognizable transaction labels. Avoid using arbitrary numbers.
    is_upi_transaction = bool(
        upi["platform"]
        or re.search(
            r"\b(UPI|money sent|money received|transaction successful|"
            r"payment successful|paid to|received from|debited|credited)\b",
            text,
            re.IGNORECASE,
        )
    )

    if is_upi_transaction:
        total_amount = upi["amount"]
        receipt_date = upi["transaction_date"]
        merchant = (
            upi["counterparty"]
            or parse_receipt_merchant(text, filename)
        )
        items = []
        warnings = list(upi["warnings"])
    else:
        merchant = parse_receipt_merchant(text, filename)
        receipt_date = parse_receipt_date(text)
        total_amount = parse_receipt_amount(text)
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

        if not parse_receipt_currency(text):
            warnings.append(
                "Currency could not be identified automatically."
            )

    result = {
        "merchant": merchant,
        "receipt_date": receipt_date,
        "total_amount": total_amount,
        "currency": upi["currency"] if is_upi_transaction else (
            parse_receipt_currency(text)
        ),
        "items": items,
        "warnings": warnings,
    }

    if is_upi_transaction:
        result["transaction"] = upi

    return result


def make_receipt_insights(parsed):
    """Create basic receipt consistency checks."""
    parsed = parsed or {}

    items = parsed.get("items") or []
    amount = parsed.get("total_amount")

    item_sum = round(
        sum(float(item.get("line_total") or 0) for item in items),
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

    transaction = parsed.get("transaction") or {}

    return {
        "item_count": len(items),
        "items_total_estimate": item_sum,
        "receipt_total": amount,
        "items_total_matches_receipt": matches_receipt,
        "review_recommended": bool(parsed.get("warnings")),
        "is_upi_transaction": bool(transaction),
        "transaction_type": transaction.get("transaction_type"),
        "payment_status": transaction.get("payment_status"),
        "transaction_reference_available": bool(
            transaction.get("transaction_reference")
        ),
        "expense_candidate": transaction.get("expense_candidate", False),
        "user_can_add_as_expense": transaction.get(
            "user_can_add_as_expense", False
        ),
    }


def process_receipt(
    filename,
    content,
    ocr_language=None,
    tesseract_cmd=None,
):
    """
    Extract text and parse a receipt or UPI screenshot in one call.

    This function does not save expenses or write to the database.
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