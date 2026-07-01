"""Shared utilities for file upload handling."""
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path


@asynccontextmanager
async def saved_upload(file) -> str:
    """Save an UploadFile to a temp file, yield the path, and clean up on exit.

    Usage:
        async with saved_upload(file) as tmp_path:
            # work with tmp_path
    """
    suffix = os.path.splitext(file.filename or "upload")[1] or ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        yield tmp_path
    finally:
        Path(tmp_path).unlink(missing_ok=True)
