"""Authentication router: login, logout, password setup, status check."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import auth

router = APIRouter(prefix="/api/auth", tags=["认证"])


class LoginRequest(BaseModel):
    password: str


class SetupRequest(BaseModel):
    password: str


@router.get("/status")
async def auth_status():
    """Return whether a password has been configured."""
    return {
        "password_set": auth.is_password_set(),
    }


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    """Authenticate and return a session token."""
    client_ip = request.client.host if request.client else "127.0.0.1"

    if not auth.check_rate_limit(client_ip):
        remaining = auth.get_lockout_remaining(client_ip)
        raise HTTPException(
            status_code=429,
            detail=f"尝试次数过多，请 {remaining} 秒后再试",
        )

    if not auth.check_password(req.password):
        auth.record_failed_attempt(client_ip)
        remaining = auth.get_lockout_remaining(client_ip)
        raise HTTPException(status_code=401, detail=f"密码错误")

    token = auth.create_token()
    return {"token": token, "password_set": auth.is_password_set()}


@router.post("/logout")
async def logout(request: Request):
    """Invalidate the current session token."""
    token = request.headers.get("x-auth-token", "")
    if token:
        auth.remove_token(token)
    return {"success": True}


@router.post("/setup")
async def setup(req: SetupRequest):
    """Set the system password (first-time setup or reset)."""
    if auth.is_password_set():
        raise HTTPException(status_code=400, detail="密码已设置，如需重置请提供旧密码")
    if not auth.set_password(req.password):
        raise HTTPException(status_code=400, detail="密码长度不能少于4位")
    token = auth.create_token()
    return {"token": token, "success": True}


class ResetRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/reset")
async def reset(req: ResetRequest):
    """Reset password with old password verification."""
    if not auth.check_password(req.old_password):
        raise HTTPException(status_code=401, detail="旧密码错误")
    if not auth.set_password(req.new_password):
        raise HTTPException(status_code=400, detail="新密码长度不能少于4位")
    return {"success": True}
