from contextlib import asynccontextmanager
import os
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette import status

from .database import init_db
from .routers import basic_data, import_data, settlement, dashboard, party_info, system, auth as auth_router, memo, bill_template, ocr
from . import auth


def _setup_logging():
    """Configure console + rotating file logging."""
    log_dir = os.environ.get("FINANCE_ROOT", "")
    if not log_dir:
        log_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(log_dir, "logs")

    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        pass

    log_file = os.path.join(log_dir, "finance-settlement.log")
    fmt_console = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fmt_file = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console — stderr, keep existing level (INFO)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(fmt_console)
        root.addHandler(console)

    # File — rotating, 10 MB per file, keep 5 backups
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        try:
            fh = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
            fh.setLevel(logging.DEBUG if os.environ.get("FINANCE_LOG_DEBUG") else logging.INFO)
            fh.setFormatter(fmt_file)
            root.addHandler(fh)
        except OSError:
            pass  # skip file logging if logs/ is unwritable

    # Suppress noisy DEBUG from third-party libs
    for _noisy in ("aiosqlite", "sqlalchemy.engine"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)


_setup_logging()
logger = logging.getLogger("finance-settlement")

# Ensure uvicorn loggers propagate to root (console + file)
for _uv_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
    _uv_logger = logging.getLogger(_uv_name)
    _uv_logger.handlers.clear()
    _uv_logger.propagate = True

FRONTEND_DIST = os.environ.get(
    "FRONTEND_DIST",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
)

_PUBLIC_PATHS = ("/api/auth/", "/api/health")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="财务结算系统",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions, log details, return safe response."""
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "服务器内部错误，请联系管理员"},
    )


_cors_origins = os.environ.get("CORS_ORIGINS", "")
if _cors_origins:
    allow_origins = [o.strip() for o in _cors_origins.split(",")]
else:
    allow_origins = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "https://localhost:5173", "https://127.0.0.1:5173",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth middleware ──
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path.startswith(_PUBLIC_PATHS):
        return await call_next(request)
    if auth.is_password_set():
        token = request.headers.get("x-auth-token", "")
        if not auth.validate_token(token):
            return JSONResponse(
                status_code=401,
                content={"detail": "未登录或登录已过期，请重新登录"},
            )
    return await call_next(request)


# ── Read-only middleware for LAN sharing ──
_local_ips = ("127.0.0.1", "::1")

@app.middleware("http")
async def readonly_middleware(request: Request, call_next):
    client_host = request.client.host if request.client else "127.0.0.1"
    is_local = client_host in _local_ips
    path = request.url.path
    method = request.method

    # Allow auth/health from anywhere
    if path.startswith("/api/auth/") or path == "/api/health":
        return await call_next(request)

    # LAN sharing toggle check
    if not is_local and not auth.get_lan_enabled():
        return JSONResponse(
            status_code=403,
            content={"detail": "局域网分享未开启，仅本机可访问"},
        )

    # Non-local write requests → 403
    if not is_local and method in ("POST", "PUT", "DELETE", "PATCH"):
        return JSONResponse(
            status_code=403,
            content={"detail": "只读模式：仅本机可编辑数据"},
        )

    # Mark responses for non-local requests so the frontend can show a banner
    response = await call_next(request)
    if not is_local:
        response.headers["X-Read-Only"] = "1"
    return response


app.include_router(auth_router.router)
app.include_router(basic_data.router)
app.include_router(import_data.router)
app.include_router(settlement.router)
app.include_router(dashboard.router)
app.include_router(party_info.router)
app.include_router(system.router)
app.include_router(memo.router)
app.include_router(bill_template.router)
app.include_router(ocr.router)

# ── QuickSDK third-party import (conditionally enabled) ──
# Enabled when QK_KEYS (JSON multi-key) or legacy QK_OPEN_ID is configured
_qk_keys = os.environ.get("QK_KEYS", "")
_qk_open_id = os.environ.get("QK_OPEN_ID", "")
if _qk_keys or _qk_open_id:
    from .routers import quicksdk
    app.include_router(quicksdk.router)
    logger.info("QuickSDK integration enabled")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Serve frontend static files ──

_assets_dir = os.path.join(FRONTEND_DIST, "assets")
if os.path.isdir(_assets_dir):
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")


@app.middleware("http")
async def _add_no_cache_header(request: Request, call_next):
    """Add Cache-Control: no-cache to all frontend static responses."""
    response = await call_next(request)
    path = request.url.path
    if not path.startswith("/api/") and not path.startswith("/docs") and not path.startswith("/openapi"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """SPA fallback: serve index.html for non-API routes."""
    if full_path.startswith("api/") or full_path.startswith("assets/"):
        from fastapi import HTTPException
        raise HTTPException(404)
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return {"error": "frontend not built, run: cd frontend && npx vite build"}
