"""Convert parsed receipt data into the existing expense-record format.

This module prepares and validates expense dictionaries. It does not
write to MongoDB or modify any other application file.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


DEFAULT_CURRENCY = "INR"
DEFAULT_CATEGORY = "Other"
RECEIPT_EXPENSE_SOURCE = "receipt_scanner"


def _to_decimal(value: Any) -> Decimal | None:
    """Convert a value to a finite Decimal."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if not value:
            return None

        value = re.sub(
            r"^(?:₹|Rs\.?|INR|USD|EUR|GBP|AED|CAD|AUD|\$|€|£)\s*",
            "",
            value,
            flags=re.IGNORECASE,
        )

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

    if not amount.is_finite():
        return None

    return amount


def _normalize_date(value: Any) -> str | None:
    """Normalize a date into YYYY-MM-DD."""
    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    # First support ISO dates and ISO timestamps.
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        pass

    supported_formats = (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%Y.%m.%d",
    )

    for fmt in supported_formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    # Ambiguous date formats are deliberately not guessed.
    return None


def _normalize_currency(
    value: Any,
    *,
    default_currency: str = DEFAULT_CURRENCY,
) -> str:
    """Return a normalized three-letter currency code."""
    if isinstance(value, str):
        currency = value.strip().upper()
        if re.fullmatch(r"[A-Z]{3}", currency):
            return currency

    fallback = str(default_currency).strip().upper()

    if not re.fullmatch(r"[A-Z]{3}", fallback):
        raise ValueError("default_currency must be a three-letter code.")

    return fallback


def _normalize_merchant(value: Any) -> str | None:
    """Normalize a merchant name."""
    if not isinstance(value, str):
        return None

    merchant = re.sub(r"\s+", " ", value).strip()
    return merchant or None


def _normalize_items(items: Any) -> list[dict[str, Any]]:
    """Normalize receipt items to the existing scanner item format.

    Supports either:
      {"name": "...", "line_total": 10.0, "quantity": 1}
    or:
      {"description": "...", "amount": 10.0, "quantity": 1}
    """
    if items is None:
        return []

    if not isinstance(items, list):
        raise ValueError("Receipt items must be provided as a list.")

    normalized_items: list[dict[str, Any]] = []

    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"Receipt item {index + 1} must be a dictionary."
            )

        raw_name = item.get("name") or item.get("description")
        name = (
            re.sub(r"\s+", " ", raw_name).strip()
            if isinstance(raw_name, str)
            else ""
        )

        raw_line_total = item.get("line_total")
        if raw_line_total is None:
            raw_line_total = item.get("amount")

        line_total = _to_decimal(raw_line_total)

        raw_quantity = item.get("quantity")
        quantity = _to_decimal(raw_quantity) if raw_quantity is not None else None

        normalized_item: dict[str, Any] = {
            "name": name or "Unknown item",
            "line_total": (
                float(line_total)
                if line_total is not None and line_total >= 0
                else None
            ),
            "quantity": (
                float(quantity)
                if quantity is not None and quantity > 0
                else None
            ),
        }

        normalized_items.append(normalized_item)

    return normalized_items


def build_expense_description(
    receipt: Mapping[str, Any],
    *,
    max_items: int = 3,
) -> str:
    """Build a readable description from merchant and item names.

    The existing expense schema does not require a description field.
    This helper can be used by a caller if a description is needed.
    """
    if isinstance(max_items, bool) or not isinstance(max_items, int):
        raise ValueError("max_items must be a non-negative integer.")

    if max_items < 0:
        raise ValueError("max_items must be a non-negative integer.")

    merchant = _normalize_merchant(receipt.get("merchant"))
    items = receipt.get("items")

    item_names: list[str] = []

    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping):
                continue

            name = item.get("name") or item.get("description")
            if isinstance(name, str) and name.strip():
                item_names.append(re.sub(r"\s+", " ", name).strip())

    parts: list[str] = []

    if merchant:
        parts.append(merchant)

    if item_names and max_items > 0:
        selected_names = item_names[:max_items]
        parts.append(", ".join(selected_names))

        remaining = len(item_names) - len(selected_names)
        if remaining > 0:
            parts.append(f"+{remaining} more item(s)")

    return " — ".join(parts) if parts else "Receipt expense"


def validate_expense_fields(
    expense: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate fields needed by the existing expense API."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(expense, Mapping):
        return {
            "valid": False,
            "errors": ["Expense data must be a dictionary or mapping."],
            "warnings": [],
        }

    amount = _to_decimal(expense.get("amount"))

    if amount is None:
        errors.append("Expense amount must be a valid finite number.")
    elif amount <= 0:
        errors.append("Expense amount must be greater than zero.")

    category = expense.get("category")
    if not isinstance(category, str) or not category.strip():
        errors.append("Expense category is required.")

    raw_date = expense.get("date")
    normalized_date = _normalize_date(raw_date)

    if normalized_date is None:
        errors.append("Expense date is missing or invalid.")

    currency = expense.get("currency")
    if (
        not isinstance(currency, str)
        or not re.fullmatch(r"[A-Za-z]{3}", currency.strip())
    ):
        errors.append("Currency must be a three-letter code.")

    if not expense.get("merchant"):
        warnings.append("Merchant name is missing.")

    if not isinstance(expense.get("items", []), list):
        errors.append("Expense items must be a list.")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def map_receipt_to_expense(
    receipt: Mapping[str, Any],
    *,
    user_id: str,
    receipt_id: str | None = None,
    default_currency: str = DEFAULT_CURRENCY,
    fallback_date: date | None = None,
) -> dict[str, Any]:
    """Map parsed receipt data to the existing expense-record schema.

    Required:
      - receipt: parsed receipt mapping
      - user_id: authenticated application's user identifier

    A missing receipt date falls back to fallback_date, or today's date.
    A warning is returned so the caller can request review.

    This function does not persist the returned dictionary.
    """
    if not isinstance(receipt, Mapping):
        raise ValueError("receipt must be a dictionary or mapping.")

    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("A non-empty user_id is required.")

    warnings: list[str] = []

    raw_amount = receipt.get("total_amount")
    if raw_amount is None:
        raw_amount = receipt.get("amount")
    if raw_amount is None:
        raw_amount = receipt.get("total")

    amount = _to_decimal(raw_amount)

    if amount is None:
        raise ValueError("Receipt does not contain a valid total amount.")

    if amount <= 0:
        raise ValueError("Receipt total amount must be greater than zero.")

    merchant = _normalize_merchant(receipt.get("merchant"))

    if not merchant:
        merchant = "Unknown merchant"
        warnings.append("Merchant could not be identified; review is needed.")

    raw_date = receipt.get("receipt_date")
    if raw_date is None:
        raw_date = receipt.get("date")

    expense_date = _normalize_date(raw_date)

    if expense_date is None:
        if raw_date:
            warnings.append(
                "Receipt date could not be parsed; a fallback date was used."
            )
        else:
            warnings.append(
                "Receipt date is missing; a fallback date was used."
            )

        selected_fallback = fallback_date or date.today()
        expense_date = selected_fallback.isoformat()

    currency_value = receipt.get("currency")
    currency = _normalize_currency(
        currency_value,
        default_currency=default_currency,
    )

    if not currency_value:
        warnings.append(
            f"Currency was not detected; {currency} was used as the default."
        )

    # Match the category heuristic currently used by app.py.
    category = (
        "Shopping"
        if re.search(
            r"(market|mart|store|supermarket|grocery|retail)",
            merchant,
            re.IGNORECASE,
        )
        else DEFAULT_CATEGORY
    )

    items = _normalize_items(receipt.get("items"))

    expense: dict[str, Any] = {
        "user_id": user_id,
        "amount": float(amount),
        "category": category,
        "currency": currency,
        "date": expense_date,
        "source": RECEIPT_EXPENSE_SOURCE,
        "merchant": merchant,
        "items": items,
    }

    if receipt_id is not None:
        if not isinstance(receipt_id, str) or not receipt_id.strip():
            raise ValueError("receipt_id must be a non-empty string.")
        expense["receipt_id"] = receipt_id.strip()

    validation = validate_expense_fields(expense)

    if not validation["valid"]:
        raise ValueError(
            "Generated expense failed validation: "
            + "; ".join(validation["errors"])
        )

    return {
        "expense": expense,
        "warnings": warnings,
        "description": build_expense_description(receipt),
        "validation": validation,
    }


def build_expense_from_receipt(
    receipt: Mapping[str, Any],
    *,
    user_id: str,
    receipt_id: str | None = None,
    default_currency: str = DEFAULT_CURRENCY,
    fallback_date: date | None = None,
) -> dict[str, Any]:
    """Public helper to prepare an expense from parsed receipt data.

    Returns a dictionary containing:
      - expense: normalized expense record
      - warnings: messages requiring user review
      - description: readable optional description
      - validation: validation result

    No database writes are performed.
    """
    return map_receipt_to_expense(
        receipt,
        user_id=user_id,
        receipt_id=receipt_id,
        default_currency=default_currency,
        fallback_date=fallback_date,
    )