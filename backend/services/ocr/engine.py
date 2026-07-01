"""OCR engine — calls the PaddleOCR bridge via HTTP.

The bridge is started/stopped manually by the user via API endpoints.
Engine only connects, never auto-launches.
"""
import time
import httpx
import subprocess
from pathlib import Path

_BRIDGE_DIR = Path(__file__).resolve().parent
_BRIDGE_SCRIPT = str(_BRIDGE_DIR / "bridge.py")
_OCR_VENV = _BRIDGE_DIR.parent.parent / "ocr_venv" / "Scripts" / "python.exe"
_PYTHON = str(_OCR_VENV) if _OCR_VENV.exists() else "python3.12"
_BRIDGE_URL = "http://127.0.0.1:8771"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
    return _client


async def bridge_health() -> dict | None:
    """Check if bridge is online. Returns health JSON or None."""
    try:
        r = await _get_client().get(f"{_BRIDGE_URL}/health")
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def start_bridge():
    """Launch the bridge process. Non-blocking."""
    subprocess.Popen(
        [_PYTHON, _BRIDGE_SCRIPT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_bridge():
    """Send shutdown to bridge."""
    import httpx as _httpx
    try:
        _httpx.post(f"{_BRIDGE_URL}/shutdown", timeout=3)
    except Exception:
        pass


async def wait_bridge_ready(timeout: int = 60) -> bool:
    """Poll until bridge responds or timeout."""
    for _ in range(timeout // 2):
        if await bridge_health():
            return True
        time.sleep(2)
    return False


async def run_ocr(image_bytes: bytes) -> list[dict]:
    """Send image to PaddleOCR bridge, return word blocks."""
    health = await bridge_health()
    if not health:
        raise RuntimeError("OCR 桥接服务未启动，请先点击「启动 OCR」按钮")

    r = await _get_client().post(
        f"{_BRIDGE_URL}/ocr",
        files={"file": ("image.png", image_bytes, "image/png")},
    )
    if r.status_code != 200:
        raise RuntimeError(f"OCR bridge error: {r.text[:300]}")
    return r.json()["data"]
