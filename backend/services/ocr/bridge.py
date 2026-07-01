"""PaddleOCR microservice on port 8771 — auto-shuts down after 10 min idle to free ~1GB RAM."""
import sys
import os
import json
import time
import asyncio
import threading
import uvicorn
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from paddleocr import PaddleOCR

IDLE_TIMEOUT = 600  # 10 min

app = FastAPI(title="PaddleOCR Bridge")
_ocr = None
_last_request = 0.0


def _touch():
    global _last_request
    _last_request = time.time()


def _get_ocr():
    global _ocr
    if _ocr is None:
        _ocr = PaddleOCR(lang="ch")
        _touch()
    return _ocr


def _idle_thread():
    while True:
        time.sleep(30)
        if _ocr is not None and time.time() - _last_request > IDLE_TIMEOUT:
            print("Idle timeout, shutting down to free memory…")
            os._exit(0)


@app.on_event("startup")
async def startup():
    threading.Thread(target=_idle_thread, daemon=True).start()


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": _ocr is not None}  # don't call _get_ocr() here


@app.post("/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "仅支持图片文件")
    image_bytes = await file.read()
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(400, "图片不能超过 20MB")

    _touch()

    tmp = Path(__file__).parent / "_ocr_temp.png"
    tmp.write_bytes(image_bytes)

    try:
        ocr = _get_ocr()
        result = ocr.predict(str(tmp))
    except Exception as e:
        raise HTTPException(500, f"OCR failed: {e}")
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass

    if not result or not result[0]:
        return {"data": []}

    raw = result[0]
    words = []

    if hasattr(raw, "get"):
        texts = raw.get("rec_texts") or []
        scores = raw.get("rec_scores") or []
        polys = raw.get("dt_polys") or []
        for i in range(len(texts)):
            poly = polys[i]
            words.append({
                "text": str(texts[i]),
                "bbox": {
                    "x0": int(min(p[0] for p in poly)),
                    "y0": int(min(p[1] for p in poly)),
                    "x1": int(max(p[0] for p in poly)),
                    "y1": int(max(p[1] for p in poly)),
                },
                "confidence": float(round(scores[i] * 100, 1)),
            })
    elif isinstance(raw, list) and len(raw) > 0:
        for line in raw:
            bbox = line[0]
            txt = line[1]
            text = txt[0] if isinstance(txt, (list, tuple)) else txt
            conf = txt[1] if isinstance(txt, (list, tuple)) and len(txt) > 1 else 0
            words.append({
                "text": str(text),
                "bbox": {
                    "x0": int(min(p[0] for p in bbox)),
                    "y0": int(min(p[1] for p in bbox)),
                    "x1": int(max(p[0] for p in bbox)),
                    "y1": int(max(p[1] for p in bbox)),
                },
                "confidence": float(round(conf * 100, 1)),
            })

    return {"data": words}


@app.post("/shutdown")
async def shutdown():
    os._exit(0)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8771
    print(f"PaddleOCR bridge starting on port {port}...")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
