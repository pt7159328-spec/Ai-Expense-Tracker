"""Parse structured receipt information from OCR-extracted text."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


DATE_PATTERNS = (
    r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b",
    r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b",
)

TOTAL_LABELS = (
    "grand total",
    "amount due",
    "total due",
    "net payable",
    "total payable",
    "invoice total",
    "total",
)

SUBTOTAL_LABELS = (
    "subtotal",
    "sub total",
    "taxable amount",
)

CURRENCY_PATTERNS = (
    (re.compile(r"₹|\bINR\b|\bRs\.?", re.IGNORECASE), "INR"),
    (re.compile(r"\$|\bUSD\b", re.IGNORECASE), "USD"),
    (re.compile(r"€|\bEUR\b", re.IGNORECASE), "EUR"),
    (re.compile(r"£|\bGBP\b", re.IGNORECASE), "GBP"),
    (re.compile(r"\bAED\b", re.IGNORECASE), "AED"),
    (re.compile(r"\bCAD\b", re.IGNORECASE), "CAD"),
    (re.compile(r"\bAUD\b", re.IGNORECASE), "AUD"),
)

AMOUNT_PATTERN = re.compile(
    r"(?<!\w)"
    r"(?:₹|Rs\.?|INR|USD|EUR|GBP|AED|CAD|AUD|\$|€|£)?\s*"
    r"(-?\d[\d,]*(?:\.\d{1,2})?)"
    r"(?!\w)",
    re.IGNORECASE,
)


def _clean_text(text: str | None) -> str:
    """Normalize OCR text without changing its overall line structure."""
    if not text:
        return ""

    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _parse_decimal(value: str) -> Decimal | None:
    """Convert a numeric string into Decimal, if possible."""
    if not value:
        return None

    normalized = value.replace(",", "").strip()

    try:
        result = Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None

    if not result.is_finite():
        return None

    return result


def _amounts_in_line(line: str) -> list[Decimal]:
    """Return numeric amounts found in a line."""
    amounts: list[Decimal] = []

    for match in AMOUNT_PATTERN.finditer(line):
        amount = _parse_decimal(match.group(1))
        if amount is not None:
            amounts.append(amount)

    return amounts


def parse_receipt_date(text: str | None) -> str | None:
    """
    Extract a receipt date and return it as YYYY-MM-DD.

    Ambiguous dates such as 03/04/2025 are interpreted as
    month/day/year when the first component exceeds 12;
    otherwise day/month/year is preferred.
    """
    normalized = _clean_text(text)

    for pattern in DATE_PATTERNS:
        match = re.search(pattern, normalized)
        if not match:
            continue

        groups = [int(value) for value in match.groups()]

        try:
            if len(str(match.group(1))) == 4:
                year, month, day = groups
            else:
                first, second, year = groups

                if year < 100:
                    year += 2000 if year < 70 else 1900

                if first > 12:
                    day, month = first, second
                elif second > 12:
                    month, day = first, second
                else:
                    day, month = first, second

            parsed = datetime(year, month, day)
            return parsed.strftime("%Y-%m-%d")
        except (ValueError, OverflowError):
            continue

    # Handle month names such as 14 Jan 2025 or January 14, 2025.
    month_patterns = (
        r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b",
        r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b",
    )

    for index, pattern in enumerate(month_patterns):
        match = re.search(pattern, normalized)
        if not match:
            continue

        try:
            if index == 0:
                date_text = (
                    f"{match.group(1)} "
                    f"{match.group(2)} "
                    f"{match.group(3)}"
                )
                parsed = datetime.strptime(date_text, "%d %B %Y")
                if parsed is None:
                    continue
            else:
                date_text = (
                    f"{match.group(1)} "
                    f"{match.group(2)} "
                    f"{match.group(3)}"
                )
                try:
                    parsed = datetime.strptime(date_text, "%B %d %Y")
                except ValueError:
                    parsed = datetime.strptime(date_text, "%b %d %Y")

            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            # Retry abbreviated/full month names where appropriate.
            try:
                if index == 0:
                    parsed = datetime.strptime(
                        f"{match.group(1)} {match.group(2)[:3]} "
                        f"{match.group(3)}",
                        "%d %b %Y",
                    )
                else:
                    parsed = datetime.strptime(
                        f"{match.group(1)[:3]} {match.group(2)} "
                        f"{match.group(3)}",
                        "%b %d %Y",
                    )
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

    return None


def parse_receipt_currency(text: str | None) -> str | None:
    """Identify a currency code from common symbols or abbreviations."""
    normalized = _clean_text(text)

    for pattern, currency_code in CURRENCY_PATTERNS:
        if pattern.search(normalized):
            return currency_code

    return None


def parse_receipt_merchant(text: str | None) -> str | None:
    """
    Guess the merchant name from the first useful receipt lines.

    This is a heuristic: OCR text alone cannot always distinguish
    a merchant name from a slogan, address, or receipt heading.
    """
    normalized = _clean_text(text)
    if not normalized:
        return None

    ignored_exact = {
        "receipt",
        "tax invoice",
        "invoice",
        "cash memo",
        "bill",
        "customer copy",
        "original",
        "duplicate",
    }

    ignored_terms = (
        "phone",
        "mobile",
        "telephone",
        "email",
        "www.",
        "http://",
        "https://",
        "invoice no",
        "invoice number",
        "receipt no",
        "receipt number",
        "gstin",
        "vat no",
        "tax id",
        "date:",
        "time:",
    )

    candidates: list[str] = []

    for raw_line in normalized.splitlines()[:12]:
        line = raw_line.strip(" \t:|")
        if not line:
            continue

        lowered = line.lower()

        if lowered in ignored_exact:
            continue

        if any(term in lowered for term in ignored_terms):
            continue

        if not re.search(r"[A-Za-z]", line):
            continue

        if len(line) < 2 or len(line) > 90:
            continue

        # Avoid selecting lines that are primarily numeric.
        letters = sum(character.isalpha() for character in line)
        if letters < 2:
            continue

        candidates.append(line)

    return candidates[0] if candidates else None


def parse_receipt_amount(text: str | None) -> float | None:
    """
    Extract the likely final payable amount.

    Prioritizes lines explicitly labelled as a total, while avoiding
    subtotal labels. If no labelled total is found, returns None
    rather than assuming that the largest number is the total.
    """
    normalized = _clean_text(text)
    if not normalized:
        return None

    lines = normalized.splitlines()

    # Search from the bottom because totals commonly appear near
    # the end of a receipt.
    for raw_line in reversed(lines):
        line = raw_line.strip()
        lowered = line.lower()

        if any(label in lowered for label in SUBTOTAL_LABELS):
            continue

        if not any(label in lowered for label in TOTAL_LABELS):
            continue

        amounts = _amounts_in_line(line)
        if not amounts:
            continue

        # The last numeric amount on a total-labelled line is
        # commonly the payable value.
        amount = amounts[-1]

        if amount < 0:
            continue

        return float(amount)

    return None


def parse_receipt_items(text: str | None) -> list[dict[str, Any]]:
    """
    Extract likely item lines.

    Receipt layouts differ significantly, so the output is heuristic.
    Each returned item contains a description and an optional amount.
    Quantity is not inferred unless it is explicitly parsed in a
    future extension.
    """
    normalized = _clean_text(text)
    if not normalized:
        return []

    items: list[dict[str, Any]] = []

    ignored_labels = (
        "subtotal",
        "sub total",
        "grand total",
        "total",
        "amount due",
        "net payable",
        "tax",
        "vat",
        "gst",
        "discount",
        "change",
        "cash",
        "card",
        "balance",
        "round off",
        "rounding",
        "payment",
        "tender",
        "invoice",
        "receipt",
        "date",
        "time",
        "phone",
        "address",
        "thank you",
    )

    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        lowered = line.lower()

        if any(label in lowered for label in ignored_labels):
            continue

        amounts = _amounts_in_line(line)
        if not amounts:
            continue

        # A line should have a meaningful description in addition
        # to the amount, rather than being only a number.
        amount_match = AMOUNT_PATTERN.search(line)
        if not amount_match:
            continue

        description = (
            line[:amount_match.start()] + line[amount_match.end():]
        ).strip(" \t-:|.")

        description = re.sub(r"\s+", " ", description)

        if len(description) < 2:
            continue

        if not re.search(r"[A-Za-z]", description):
            continue

        amount = amounts[-1]
        if amount < 0:
            continue

        items.append(
            {
                "description": description,
                "quantity": None,
                "amount": float(amount),
            }
        )

    return items


def parse_receipt(text: str | None) -> dict[str, Any]:
    """
    Parse OCR text into a consistent receipt-data dictionary.

    This function does not perform OCR and does not save data to a
    database. It only interprets text supplied by the caller.
    """
    normalized = _clean_text(text)

    return {
        "merchant": parse_receipt_merchant(normalized),
        "date": parse_receipt_date(normalized),
        "total_amount": parse_receipt_amount(normalized),
        "currency": parse_receipt_currency(normalized),
        "items": parse_receipt_items(normalized),
        "raw_text": normalized,
    }


def make_receipt_insights(
    receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Generate basic insights from parsed receipt data.

    Insights are limited to fields present in the supplied dictionary;
    this function does not access a database or external service.
    """
    if not isinstance(receipt, dict):
        return {
            "has_merchant": False,
            "has_date": False,
            "has_total": False,
            "item_count": 0,
            "items_total": None,
            "total_minus_items": None,
            "warnings": ["No parsed receipt data was provided."],
        }

    merchant = receipt.get("merchant")
    receipt_date = receipt.get("date")
    total_amount = receipt.get("total_amount")
    items = receipt.get("items")

    if not isinstance(items, list):
        items = []

    valid_item_amounts: list[Decimal] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        value = item.get("amount")
        if value is None:
            continue

        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            continue

        if amount.is_finite() and amount >= 0:
            valid_item_amounts.append(amount)

    items_total: float | None = None
    total_minus_items: float | None = None
    parsed_total: Decimal | None = None

    if valid_item_amounts:
        items_total_decimal = sum(valid_item_amounts, Decimal("0"))
        items_total = float(items_total_decimal)

    if total_amount is not None:
        try:
            parsed_total = Decimal(str(total_amount))
        except (InvalidOperation, ValueError):
            parsed_total = None

    if (
        parsed_total is not None
        and parsed_total.is_finite()
        and items_total is not None
    ):
        total_minus_items = float(
            parsed_total - Decimal(str(items_total))
        )

    warnings: list[str] = []

    if not merchant:
        warnings.append("Merchant could not be identified confidently.")

    if not receipt_date:
        warnings.append("Receipt date could not be identified.")

    if total_amount is None:
        warnings.append("A labelled total amount was not found.")

    if not items:
        warnings.append("No likely line items were extracted.")

    if total_minus_items is not None and abs(total_minus_items) > 0.02:
        warnings.append(
            "The sum of extracted item amounts differs from the receipt total."
        )

    return {
        "has_merchant": bool(merchant),
        "has_date": bool(receipt_date),
        "has_total": total_amount is not None,
        "item_count": len(items),
        "items_total": items_total,
        "total_minus_items": total_minus_items,
        "warnings": warnings,
    }