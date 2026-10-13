"""Utilities for detecting potentially duplicate receipts.

This module performs in-memory comparisons only. It does not access a
database, modify receipt records, or delete duplicates.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


def _normalize_text(value: Any) -> str | None:
    """Normalize text for comparison."""
    if not isinstance(value, str):
        return None

    normalized = re.sub(r"\s+", " ", value.strip().casefold())
    return normalized or None


def _normalize_merchant(value: Any) -> str | None:
    """Normalize merchant names while ignoring basic punctuation."""
    normalized = _normalize_text(value)
    if not normalized:
        return None

    normalized = re.sub(r"[^\w\s]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized or None


def _normalize_date(value: Any) -> str | None:
    """Normalize common ISO-style receipt dates."""
    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    # Prefer an ISO date prefix when the input includes a timestamp.
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
    if match:
        return match.group(1)

    # Do not guess the meaning of ambiguous dates such as 03/04/2025.
    return None


def _normalize_amount(value: Any) -> str | None:
    """Normalize a non-negative amount to two decimal places."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

        value = re.sub(
            r"^(?:₹|Rs\.?|INR|USD|EUR|GBP|AED|CAD|AUD|\$|€|£)\s*",
            "",
            value,
            flags=re.IGNORECASE,
        )
        value = value.replace(",", "").strip()

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

    if not amount.is_finite() or amount < 0:
        return None

    return format(amount.quantize(Decimal("0.01")), "f")


def _normalize_receipt_number(value: Any) -> str | None:
    """Normalize an explicit receipt or invoice number."""
    normalized = _normalize_text(value)
    if not normalized:
        return None

    # Remove spaces and separators commonly introduced by OCR.
    normalized = re.sub(r"[\s\-_/]+", "", normalized)
    return normalized or None


def normalize_receipt_data(
    receipt: Mapping[str, Any] | None,
) -> dict[str, str | None]:
    """Return normalized fields used for duplicate comparison.

    Supports common field names:
    - merchant
    - date or receipt_date
    - total_amount, total, or amount
    - receipt_number, invoice_number, or invoice_no
    - currency
    """
    if not isinstance(receipt, Mapping):
        return {
            "merchant": None,
            "date": None,
            "total_amount": None,
            "currency": None,
            "receipt_number": None,
        }

    merchant = receipt.get("merchant")

    raw_date = receipt.get("date")
    if raw_date is None:
        raw_date = receipt.get("receipt_date")

    raw_amount = receipt.get("total_amount")
    if raw_amount is None:
        raw_amount = receipt.get("total")
    if raw_amount is None:
        raw_amount = receipt.get("amount")

    raw_currency = receipt.get("currency")

    raw_receipt_number = receipt.get("receipt_number")
    if raw_receipt_number is None:
        raw_receipt_number = receipt.get("invoice_number")
    if raw_receipt_number is None:
        raw_receipt_number = receipt.get("invoice_no")

    currency = _normalize_text(raw_currency)
    if currency:
        currency = currency.upper()

    return {
        "merchant": _normalize_merchant(merchant),
        "date": _normalize_date(raw_date),
        "total_amount": _normalize_amount(raw_amount),
        "currency": currency,
        "receipt_number": _normalize_receipt_number(raw_receipt_number),
    }


def generate_receipt_fingerprint(
    receipt: Mapping[str, Any] | None,
) -> str | None:
    """Generate a deterministic fingerprint from available receipt fields.

    Returns None when too little identifying information is available.
    The fingerprint is useful for comparison, but is not proof that two
    receipts represent the same purchase.
    """
    normalized = normalize_receipt_data(receipt)

    # Receipt number is a strong identifier when accompanied by merchant.
    if normalized["receipt_number"] and normalized["merchant"]:
        fingerprint_fields = {
            "merchant": normalized["merchant"],
            "receipt_number": normalized["receipt_number"],
        }
    else:
        # Fall back to merchant, date, and amount.
        required_fields = (
            normalized["merchant"],
            normalized["date"],
            normalized["total_amount"],
        )

        if not all(required_fields):
            return None

        fingerprint_fields = {
            "merchant": normalized["merchant"],
            "date": normalized["date"],
            "total_amount": normalized["total_amount"],
            "currency": normalized["currency"],
        }

    serialized = json.dumps(
        fingerprint_fields,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compare_receipts(
    first: Mapping[str, Any] | None,
    second: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare two receipts and explain the evidence for a possible match."""
    left = normalize_receipt_data(first)
    right = normalize_receipt_data(second)

    matched_fields: list[str] = []
    differing_fields: list[str] = []
    unavailable_fields: list[str] = []

    comparison_fields = (
        "merchant",
        "date",
        "total_amount",
        "currency",
        "receipt_number",
    )

    for field in comparison_fields:
        left_value = left[field]
        right_value = right[field]

        if left_value is None or right_value is None:
            unavailable_fields.append(field)
        elif left_value == right_value:
            matched_fields.append(field)
        else:
            differing_fields.append(field)

    # Currency mismatches are significant when both currencies are known.
    currency_conflict = "currency" in differing_fields

    # A shared receipt number and merchant is strong matching evidence.
    strong_match = (
        "receipt_number" in matched_fields
        and "merchant" in matched_fields
        and not currency_conflict
    )

    # The fallback requires all three key fields to match.
    fallback_match = all(
        field in matched_fields
        for field in ("merchant", "date", "total_amount")
    ) and not currency_conflict

    possible_duplicate = strong_match or fallback_match

    if strong_match:
        confidence = "high"
        reason = "Merchant and receipt number match."
    elif fallback_match:
        confidence = "medium"
        reason = "Merchant, date, and total amount match."
    else:
        confidence = "low"
        reason = "There is insufficient matching evidence."

    if differing_fields:
        reason += " Some available fields differ."

    return {
        "possible_duplicate": possible_duplicate,
        "confidence": confidence,
        "reason": reason,
        "matched_fields": matched_fields,
        "differing_fields": differing_fields,
        "unavailable_fields": unavailable_fields,
        "first_fingerprint": generate_receipt_fingerprint(first),
        "second_fingerprint": generate_receipt_fingerprint(second),
    }


def find_duplicate_receipts(
    receipts: Sequence[Mapping[str, Any]],
    *,
    id_field: str = "id",
) -> list[dict[str, Any]]:
    """Find pairs of potentially duplicate receipts in a collection.

    The input is not modified. Each result includes the original receipt
    identifiers where available and the comparison evidence.

    Receipts without sufficient matching fields are not automatically
    classified as duplicates.
    """
    if isinstance(receipts, (str, bytes)) or not isinstance(
        receipts, Sequence
    ):
        raise TypeError("receipts must be a sequence of receipt mappings.")

    results: list[dict[str, Any]] = []

    for index, first in enumerate(receipts):
        if not isinstance(first, Mapping):
            continue

        for second_index in range(index + 1, len(receipts)):
            second = receipts[second_index]

            if not isinstance(second, Mapping):
                continue

            comparison = compare_receipts(first, second)

            if not comparison["possible_duplicate"]:
                continue

            results.append(
                {
                    "first_index": index,
                    "second_index": second_index,
                    "first_id": first.get(id_field),
                    "second_id": second.get(id_field),
                    **comparison,
                }
            )

    return results


def group_receipts_by_fingerprint(
    receipts: Sequence[Mapping[str, Any]],
    *,
    id_field: str = "id",
) -> list[dict[str, Any]]:
    """Group receipts that share an exact generated fingerprint.

    This is a stricter grouping operation than fuzzy duplicate matching.
    Receipts without a usable fingerprint are omitted.
    """
    if isinstance(receipts, (str, bytes)) or not isinstance(
        receipts, Sequence
    ):
        raise TypeError("receipts must be a sequence of receipt mappings.")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for index, receipt in enumerate(receipts):
        if not isinstance(receipt, Mapping):
            continue

        fingerprint = generate_receipt_fingerprint(receipt)
        if fingerprint is None:
            continue

        groups[fingerprint].append(
            {
                "index": index,
                "id": receipt.get(id_field),
            }
        )

    return [
        {
            "fingerprint": fingerprint,
            "receipts": members,
            "count": len(members),
        }
        for fingerprint, members in groups.items()
        if len(members) > 1
    ]