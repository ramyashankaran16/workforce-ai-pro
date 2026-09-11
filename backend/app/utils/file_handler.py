"""
Upload validation and safe storage.

Extension checking alone is not validation: anything can be renamed to .pdf.
The magic-byte check reads the first few bytes and confirms the file is what it
claims to be, which stops the most obvious upload attack -- a script with a
document extension.
"""

import os
import re
import uuid
from typing import Dict, Optional, Set, Tuple

from app.core.exceptions import ValidationError

# First bytes that identify a format, keyed by extension.
MAGIC_BYTES: Dict[str, Tuple[bytes, ...]] = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    # docx/xlsx are zip containers
    "docx": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",),
    "zip": (b"PK\x03\x04",),
}

# Extensions that must never be accepted whatever else is true.
BLOCKED_EXTENSIONS: Set[str] = {
    "exe", "dll", "bat", "cmd", "com", "scr", "msi", "vbs", "js", "jar",
    "sh", "ps1", "app", "deb", "rpm", "php", "asp", "aspx", "jsp", "py",
}

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def extension_of(filename: str) -> str:
    return (os.path.splitext(filename or "")[1] or "").lstrip(".").lower()


def safe_filename(filename: str) -> str:
    """Strip directory components and anything that could escape the folder."""
    base = os.path.basename(filename or "upload")
    base = SAFE_NAME.sub("_", base)
    base = base.lstrip(".") or "upload"
    return base[:120]


def unique_path(directory: str, filename: str) -> str:
    os.makedirs(directory, exist_ok=True)
    stem, suffix = os.path.splitext(safe_filename(filename))
    return os.path.join(directory, f"{stem}_{uuid.uuid4().hex[:10]}{suffix}")


def validate_upload(
    content: bytes,
    filename: str,
    allowed_extensions: Set[str],
    max_size_mb: int,
) -> str:
    """Run every check and return the normalised extension."""
    if not content:
        raise ValidationError("The uploaded file is empty.")

    max_bytes = max_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        actual = len(content) / (1024 * 1024)
        raise ValidationError(
            f"File is {actual:.1f} MB; the limit is {max_size_mb} MB."
        )

    extension = extension_of(filename)
    if not extension:
        raise ValidationError("The file has no extension.")

    if extension in BLOCKED_EXTENSIONS:
        raise ValidationError(f".{extension} files are not accepted.")

    allowed = {e.strip().lower().lstrip(".") for e in allowed_extensions}
    if allowed and extension not in allowed:
        raise ValidationError(
            f".{extension} is not allowed here. Accepted: {', '.join(sorted(allowed))}."
        )

    # Double extension, e.g. report.pdf.exe
    parts = safe_filename(filename).lower().split(".")
    if len(parts) > 2 and any(part in BLOCKED_EXTENSIONS for part in parts[1:-1]):
        raise ValidationError("That filename contains a blocked extension.")

    signatures = MAGIC_BYTES.get(extension)
    if signatures and not any(content.startswith(sig) for sig in signatures):
        raise ValidationError(
            f"The file content does not match a .{extension} file. "
            "Renaming a file does not change its type."
        )

    return extension


def write_file(content: bytes, directory: str, filename: str) -> Tuple[str, int]:
    path = unique_path(directory, filename)
    with open(path, "wb") as handle:
        handle.write(content)
    return path, len(content)


def delete_file(path: Optional[str]) -> bool:
    if path and os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            return False
    return False
