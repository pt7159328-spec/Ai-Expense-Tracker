"""Local storage utilities for receipt files.

This module validates supported receipt files and provides functions
to save, read, and delete them from a dedicated storage directory.

It does not connect to the database or modify other application files.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import tempfile
import uuid

from pathlib import Path
from typing import Any, Iterable


DEFAULT_MAX_BYTES = 10 * 1024 * 1024

DEFAULT_ALLOWED_EXTENSIONS = frozenset(
    {
        "png",
        "jpg",
        "jpeg",
        "webp",
        "bmp",
        "tif",
        "tiff",
        "pdf",
    }
)

FILE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "webp": (b"RIFF",),
    "bmp": (b"BM",),
    "tif": (b"II*\x00", b"MM\x00*"),
    "tiff": (b"II*\x00", b"MM\x00*"),
    "pdf": (b"%PDF-",),
}


class ReceiptStorageError(Exception):
    """Base exception for receipt storage errors."""


class InvalidReceiptFileError(ReceiptStorageError):
    """Raised when a receipt file fails validation."""


class ReceiptNotFoundError(ReceiptStorageError):
    """Raised when a requested stored receipt does not exist."""


def _get_storage_directory(
    storage_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Resolve the configured receipt storage directory."""
    if storage_dir is not None:
        directory = Path(storage_dir).expanduser()
    else:
        configured_dir = os.getenv("RECEIPT_STORAGE_DIR")

        if configured_dir:
            directory = Path(configured_dir).expanduser()
        else:
            directory = Path("instance") / "receipts"

    return directory.resolve()


def _normalize_allowed_extensions(
    allowed_extensions: Iterable[str] | None = None,
) -> frozenset[str]:
    """Normalize allowed extensions."""
    source = (
        allowed_extensions
        if allowed_extensions is not None
        else DEFAULT_ALLOWED_EXTENSIONS
    )

    normalized = frozenset(
        str(extension).strip().lower().lstrip(".")
        for extension in source
        if str(extension).strip()
    )

    if not normalized:
        raise ValueError("At least one allowed extension is required.")

    return normalized


def _get_extension(filename: str) -> str:
    """Extract the lowercase extension from a filename."""
    if not isinstance(filename, str) or not filename.strip():
        raise InvalidReceiptFileError("A filename is required.")

    # Handle both Windows and POSIX path separators.
    base_name = filename.replace("\\", "/").rsplit("/", 1)[-1]

    if "." not in base_name:
        raise InvalidReceiptFileError(
            "The receipt filename must include a file extension."
        )

    extension = base_name.rsplit(".", 1)[-1].lower()

    if not re.fullmatch(r"[a-z0-9]{1,10}", extension):
        raise InvalidReceiptFileError("The file extension is invalid.")

    return extension


def _validate_content_signature(
    extension: str,
    content: bytes,
) -> None:
    """Check that file content begins with the expected signature."""
    signatures = FILE_SIGNATURES.get(extension)

    if not signatures:
        raise InvalidReceiptFileError(
            f"File signature validation is not configured for .{extension}."
        )

    if not any(content.startswith(signature) for signature in signatures):
        raise InvalidReceiptFileError(
            "File content does not match its declared file type."
        )

    if extension == "webp":
        if len(content) < 12 or content[8:12] != b"WEBP":
            raise InvalidReceiptFileError(
                "The uploaded file does not appear to be a valid WEBP file."
            )


def validate_receipt_file(
    filename: str,
    content: bytes,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allowed_extensions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate filename, size, extension, and file signature.

    Returns normalized file metadata. The supplied content is not saved.
    """
    if not isinstance(content, bytes):
        raise InvalidReceiptFileError(
            "Receipt content must be supplied as bytes."
        )

    if not content:
        raise InvalidReceiptFileError("The receipt file is empty.")

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        raise ValueError("max_bytes must be a positive integer.")

    if max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer.")

    if len(content) > max_bytes:
        raise InvalidReceiptFileError(
            f"The receipt exceeds the maximum size of {max_bytes} bytes."
        )

    extension = _get_extension(filename)
    allowed = _normalize_allowed_extensions(allowed_extensions)

    if extension not in allowed:
        raise InvalidReceiptFileError(
            f"Unsupported receipt extension: .{extension}."
        )

    _validate_content_signature(extension, content)

    original_name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    original_name = original_name.strip()

    if not original_name:
        raise InvalidReceiptFileError("The receipt filename is invalid.")

    return {
        "original_filename": original_name,
        "extension": extension,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "content_type": (
            "application/pdf"
            if extension == "pdf"
            else mimetypes.guess_type(f"receipt.{extension}")[0]
            or "application/octet-stream"
        ),
    }


def _receipt_path(
    receipt_id: str,
    storage_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Resolve a storage path from a UUID receipt identifier."""
    if not isinstance(receipt_id, str):
        raise ValueError("receipt_id must be a UUID string.")

    try:
        parsed_id = uuid.UUID(receipt_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Invalid receipt storage identifier.") from exc

    # Require the canonical UUID representation. User input is never
    # interpreted as a filename or arbitrary filesystem path.
    if str(parsed_id) != receipt_id.lower():
        raise ValueError("Invalid receipt storage identifier.")

    directory = _get_storage_directory(storage_dir)

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReceiptStorageError(
            "Could not access the receipt storage directory."
        ) from exc

    matches = list(directory.glob(f"{parsed_id}.*"))

    if len(matches) > 1:
        raise ReceiptStorageError(
            "Multiple files were found for one receipt identifier."
        )

    if matches:
        candidate = matches[0]

        # Refuse symlinks and ensure the file stays directly inside
        # the configured storage directory.
        if candidate.is_symlink() or candidate.parent.resolve() != directory:
            raise ReceiptStorageError(
                "The receipt storage path failed a security check."
            )

        return candidate

    # Return a predictable, contained path for a missing receipt.
    return directory / f"{parsed_id}.missing"


def save_receipt_file(
    filename: str,
    content: bytes,
    *,
    storage_dir: str | os.PathLike[str] | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allowed_extensions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate and save a receipt using a generated UUID filename.

    Returns metadata including the storage identifier and content hash.
    Existing files are not overwritten.
    """
    metadata = validate_receipt_file(
        filename,
        content,
        max_bytes=max_bytes,
        allowed_extensions=allowed_extensions,
    )

    directory = _get_storage_directory(storage_dir)

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReceiptStorageError(
            "Could not create the receipt storage directory."
        ) from exc

    receipt_id = str(uuid.uuid4())
    destination = directory / f"{receipt_id}.{metadata['extension']}"

    temporary_path: Path | None = None

    try:
        # Write to a temporary file in the same directory, then atomically
        # move it into place. UUID names reduce collision risk.
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".receipt-",
            suffix=".tmp",
            dir=directory,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        # Hard-link creation fails if the destination already exists.
        # This avoids replacing an existing file.
        os.link(temporary_path, destination)
        temporary_path.unlink()
        temporary_path = None

    except OSError as exc:
        raise ReceiptStorageError(
            "Could not save the receipt file."
        ) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    return {
        "receipt_id": receipt_id,
        **metadata,
        "stored_filename": destination.name,
    }


def load_receipt_file(
    receipt_id: str,
    *,
    storage_dir: str | os.PathLike[str] | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Load a stored receipt and return its bytes and basic metadata."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        raise ValueError("max_bytes must be a positive integer.")

    if max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer.")

    directory = _get_storage_directory(storage_dir)

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReceiptStorageError(
            "Could not access the receipt storage directory."
        ) from exc

    # Find the file by canonical UUID, without accepting a path from callers.
    try:
        parsed_id = uuid.UUID(receipt_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Invalid receipt storage identifier.") from exc

    if str(parsed_id) != receipt_id.lower():
        raise ValueError("Invalid receipt storage identifier.")

    matches = list(directory.glob(f"{parsed_id}.*"))

    if not matches:
        raise ReceiptNotFoundError("Receipt file was not found.")

    if len(matches) != 1:
        raise ReceiptStorageError(
            "Multiple files were found for one receipt identifier."
        )

    path = matches[0]

    if path.is_symlink() or path.parent.resolve() != directory:
        raise ReceiptStorageError(
            "The receipt storage path failed a security check."
        )

    try:
        size = path.stat().st_size
        if size <= 0:
            raise InvalidReceiptFileError("The stored receipt is empty.")

        if size > max_bytes:
            raise InvalidReceiptFileError(
                "The stored receipt exceeds the configured size limit."
            )

        content = path.read_bytes()
    except OSError as exc:
        raise ReceiptStorageError("Could not read the receipt file.") from exc

    extension = path.suffix.lstrip(".").lower()
    _validate_content_signature(extension, content)

    return {
        "receipt_id": str(parsed_id),
        "stored_filename": path.name,
        "extension": extension,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "content_type": (
            "application/pdf"
            if extension == "pdf"
            else mimetypes.guess_type(path.name)[0]
            or "application/octet-stream"
        ),
        "content": content,
    }


def delete_receipt_file(
    receipt_id: str,
    *,
    storage_dir: str | os.PathLike[str] | None = None,
) -> bool:
    """Delete one stored receipt by its UUID.

    Returns True when a file was deleted. Raises ReceiptNotFoundError
    if no matching receipt exists.
    """
    directory = _get_storage_directory(storage_dir)

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReceiptStorageError(
            "Could not access the receipt storage directory."
        ) from exc

    try:
        parsed_id = uuid.UUID(receipt_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Invalid receipt storage identifier.") from exc

    if str(parsed_id) != receipt_id.lower():
        raise ValueError("Invalid receipt storage identifier.")

    matches = list(directory.glob(f"{parsed_id}.*"))

    if not matches:
        raise ReceiptNotFoundError("Receipt file was not found.")

    if len(matches) != 1:
        raise ReceiptStorageError(
            "Multiple files were found for one receipt identifier."
        )

    path = matches[0]

    if path.is_symlink() or path.parent.resolve() != directory:
        raise ReceiptStorageError(
            "The receipt storage path failed a security check."
        )

    try:
        path.unlink()
    except OSError as exc:
        raise ReceiptStorageError("Could not delete the receipt file.") from exc

    return True