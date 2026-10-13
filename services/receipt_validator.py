"""Validation helpers for parsed receipt data.

This module validates structured receipt data without performing OCR,
writing to a database, or modifying other application files.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


AMOUNT_TOLERANCE = Decimal("0.02")


def _to_decimal(value: Any) -> Decimal | None:
    """Convert a numeric value to Decimal, returning None if invalid."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

        # Accept common currency symbols and grouping commas.
        value = re.sub(r"^(?:₹|Rs\.?|INR|USD|EUR|GBP|AED|CAD|AUD|\$|€|£)\s*",
                       "", value, flags=re.IGNORECASE)
        value = value.replace(",", "").strip()

    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

    if not result.is_finite():
        return None

    return result


def _normalize_date(value: Any) -> date | None:
    """Parse common, explicit date formats without guessing ambiguous dates."""
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    formats = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d-%m-%y",
        "%d/%m/%y",
        "%d.%m.%y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    )

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def validate_receipt_amount(
    amount: Any,
    *,
    field_name: str = "total_amount",
    allow_zero: bool = False,
) -> dict[str, Any]:
    """Validate a receipt amount and return a structured result."""
    errors: list[str] = []
    warnings: list[str] = []
    parsed = _to_decimal(amount)

    if amount is None or (isinstance(amount, str) and not amount.strip()):
        errors.append(f"{field_name} is missing.")
    elif parsed is None:
        errors.append(f"{field_name} must be a valid finite number.")
    elif parsed < 0:
        errors.append(f"{field_name} cannot be negative.")
    elif parsed == 0 and not allow_zero:
        warnings.append(f"{field_name} is zero; please verify the receipt.")

    return {
        "valid": not errors,
        "value": float(parsed) if parsed is not None else None,
        "errors": errors,
        "warnings": warnings,
    }


def validate_receipt_date(
    value: Any,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Validate a receipt date and flag dates in the future."""
    errors: list[str] = []
    warnings: list[str] = []

    parsed = _normalize_date(value)

    if value is None or (isinstance(value, str) and not value.strip()):
        warnings.append("Receipt date is missing.")
    elif parsed is None:
        errors.append("Receipt date is invalid or uses an unsupported format.")
    else:
        comparison_date = today or date.today()
        if parsed > comparison_date:
            warnings.append("Receipt date is in the future; please verify it.")

    return {
        "valid": not errors,
        "value": parsed.isoformat() if parsed is not None else None,
        "errors": errors,
        "warnings": warnings,
    }


def validate_receipt_items(
    items: Any,
) -> dict[str, Any]:
    """Validate a list of receipt items.

    Supports common field names used by receipt parsing modules:
    name/description, line_total/amount, quantity, and unit_price.
    """
    errors: list[str] = []
    warnings: list[str] = []
    normalized_items: list[dict[str, Any]] = []

    if items is None:
        return {
            "valid": True,
            "items": [],
            "item_count": 0,
            "errors": [],
            "warnings": ["Receipt items were not provided."],
        }

    if not isinstance(items, list):
        return {
            "valid": False,
            "items": [],
            "item_count": 0,
            "errors": ["items must be a list."],
            "warnings": [],
        }

    for index, item in enumerate(items):
        prefix = f"Item {index + 1}"

        if not isinstance(item, Mapping):
            errors.append(f"{prefix} must be an object or mapping.")
            continue

        name = item.get("name") or item.get("description")
        if not isinstance(name, str) or not name.strip():
            warnings.append(f"{prefix} has no item name or description.")

        raw_amount = item.get("line_total")
        if raw_amount is None:
            raw_amount = item.get("amount")

        amount = _to_decimal(raw_amount)

        if raw_amount is None:
            warnings.append(f"{prefix} has no line total.")
        elif amount is None:
            errors.append(f"{prefix} has an invalid line total.")
        elif amount < 0:
            errors.append(f"{prefix} has a negative line total.")

        raw_quantity = item.get("quantity")
        quantity: Decimal | None = None

        if raw_quantity is not None:
            quantity = _to_decimal(raw_quantity)

            if quantity is None or quantity <= 0:
                errors.append(f"{prefix} has an invalid quantity.")

        raw_unit_price = item.get("unit_price")
        unit_price = _to_decimal(raw_unit_price)

        if raw_unit_price is not None:
            if unit_price is None:
                errors.append(f"{prefix} has an invalid unit price.")
            elif unit_price < 0:
                errors.append(f"{prefix} has a negative unit price.")

        normalized_items.append(
            {
                "name": name.strip()
                if isinstance(name, str) and name.strip()
                else None,
                "quantity": float(quantity) if quantity is not None else None,
                "unit_price": (
                    float(unit_price) if unit_price is not None else None
                ),
                "line_total": (
                    float(amount)
                    if amount is not None and amount >= 0
                    else None
                ),
            }
        )

    return {
        "valid": not errors,
        "items": normalized_items,
        "item_count": len(items),
        "errors": errors,
        "warnings": warnings,
    }


def validate_receipt_consistency(
    total_amount: Any,
    items: Any,
    *,
    tolerance: Decimal = AMOUNT_TOLERANCE,
) -> dict[str, Any]:
    """Compare the receipt total with the sum of available item amounts."""
    errors: list[str] = []
    warnings: list[str] = []

    total = _to_decimal(total_amount)

    if total is None:
        return {
            "valid": False,
            "items_total": None,
            "receipt_total": None,
            "difference": None,
            "errors": ["A valid receipt total is required for comparison."],
            "warnings": [],
        }

    if total < 0:
        return {
            "valid": False,
            "items_total": None,
            "receipt_total": float(total),
            "difference": None,
            "errors": ["Receipt total cannot be negative."],
            "warnings": [],
        }

    if not isinstance(items, list):
        return {
            "valid": False,
            "items_total": None,
            "receipt_total": float(total),
            "difference": None,
            "errors": ["items must be a list."],
            "warnings": [],
        }

    item_amounts: list[Decimal] = []

    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            warnings.append(
                f"Item {index + 1} was skipped during total comparison."
            )
            continue

        raw_amount = item.get("line_total")
        if raw_amount is None:
            raw_amount = item.get("amount")

        amount = _to_decimal(raw_amount)

        if amount is None or amount < 0:
            warnings.append(
                f"Item {index + 1} has no usable line total."
            )
            continue

        item_amounts.append(amount)

    if not item_amounts:
        return {
            "valid": True,
            "items_total": None,
            "receipt_total": float(total),
            "difference": None,
            "errors": [],
            "warnings": warnings + [
                "No usable item amounts were available for comparison."
            ],
        }

    items_total = sum(item_amounts, Decimal("0"))
    difference = total - items_total

    if abs(difference) > tolerance:
        warnings.append(
            "The sum of item amounts differs from the receipt total. "
            "Tax, discounts, missing items, or OCR errors may explain "
            "the difference."
        )

    return {
        "valid": True,
        "items_total": float(items_total),
        "receipt_total": float(total),
        "difference": float(difference),
        "errors": errors,
        "warnings": warnings,
    }


def validate_receipt_data(
    receipt: Mapping[str, Any] | None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Validate the main fields of a parsed receipt.

    Expected fields may include merchant, date, total_amount (or total),
    currency, and items. This function does not save or alter the input.
    """
    if not isinstance(receipt, Mapping):
        return {
            "valid": False,
            "errors": ["Receipt data must be a mapping or dictionary."],
            "warnings": [],
            "fields": {},
            "consistency": None,
        }

    errors: list[str] = []
    warnings: list[str] = []

    merchant = receipt.get("merchant")
    if not isinstance(merchant, str) or not merchant.strip():
        warnings.append("Merchant name is missing or could not be identified.")

    raw_date = receipt.get("date")
    date_result = validate_receipt_date(raw_date, today=today)

    errors.extend(date_result["errors"])
    warnings.extend(date_result["warnings"])

    raw_total = receipt.get("total_amount")
    if raw_total is None:
        raw_total = receipt.get("total")

    amount_result = validate_receipt_amount(raw_total)
    errors.extend(amount_result["errors"])
    warnings.extend(amount_result["warnings"])

    raw_items = receipt.get("items")
    items_result = validate_receipt_items(raw_items)

    errors.extend(items_result["errors"])
    warnings.extend(items_result["warnings"])

    currency = receipt.get("currency")
    if currency is not None:
        if not isinstance(currency, str) or not re.fullmatch(
            r"[A-Za-z]{3}", currency.strip()
        ):
            warnings.append(
                "Currency should be a three-letter currency code, "
                "such as INR or USD."
            )

    consistency = None

    if raw_total is not None and isinstance(raw_items, list):
        consistency = validate_receipt_consistency(
            raw_total,
            raw_items,
        )
        errors.extend(consistency["errors"])
        warnings.extend(consistency["warnings"])

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "fields": {
            "merchant": {
                "valid": isinstance(merchant, str) and bool(merchant.strip()),
                "value": merchant.strip()
                if isinstance(merchant, str)
                else None,
            },
            "date": date_result,
            "total_amount": amount_result,
            "items": items_result,
            "currency": {
                "valid": currency is None
                or (
                    isinstance(currency, str)
                    and bool(re.fullmatch(r"[A-Za-z]{3}", currency.strip()))
                ),
                "value": currency.strip().upper()
                if isinstance(currency, str)
                else None,
            },
        },
        "consistency": consistency,
    }