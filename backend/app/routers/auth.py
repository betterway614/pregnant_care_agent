"""认证 API - JWT + bcrypt"""
import os
import time
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from ..database import SessionLocal
from ..models import Pregnant
from ..core.auth import (
    hash_password, verify_password, create_token,
    TokenPayload, get_current_user, security,
)

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])

_login_attempts: dict[str, list[float]] = defaultdict(list)
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 60

def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _login_attempts[ip] if now - t < _LOGIN_WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    if len(attempts) >= _MAX_LOGIN_ATTEMPTS:
        return False
    _login_attempts[ip].append(now)
    return True

_PWD_PREGNANT = os.environ.get("DEMO_PASSWORD_PREGNANT", "pregnant_demo_2026")
_PWD_NURSE = os.environ.get("DEMO_PASSWORD_NURSE", "nurse_demo_2026")
_PWD_DOCTOR = os.environ.get("DEMO_PASSWORD_DOCTOR", "doctor_demo_2026")
_PWD_ADMIN = os.environ.get("DEMO_PASSWORD_ADMIN", "admin_demo_2026")

# Pre-hash passwords at module load for fast verification
_HASH_PREGNANT = hash_password(_PWD_PREGNANT)
_HASH_NURSE = hash_password(_PWD_NURSE)
_HASH_DOCTOR = hash_password(_PWD_DOCTOR)
_HASH_ADMIN = hash_password(_PWD_ADMIN)


class LoginRequest(BaseModel):
    hospital_id: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: str = ""
    role: str = ""
    pregnant_id: str = ""
    display_name: str = ""
    nickname: str = ""
    hospital_id: str = ""
    message: str = ""


@router.post("/login", response_model=LoginResponse)
def login(request: Request, req: LoginRequest):
    """登录：医院ID + 密码，返回JWT token"""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail=f"登录尝试过于频繁，请 {_LOGIN_WINDOW_SECONDS} 秒后重试")
    hid = req.hospital_id.strip()
    pwd = req.password.strip()
    if not hid or not pwd:
        return LoginResponse(success=False, message="请输入账号和密码")

    # 内置账号：admin / nurse / doctor
    _accounts = {
        "admin": ("admin", _HASH_ADMIN, "管理员", "Admin"),
        "nurse": ("nurse", _HASH_NURSE, "护士长", "小护"),
        "doctor": ("doctor", _HASH_DOCTOR, "主任医师", "Dr.智"),
    }
    if hid in _accounts:
        role, hashed, display, nick = _accounts[hid]
        if not verify_password(pwd, hashed):
            return LoginResponse(success=False, message="密码错误")
        token = create_token(TokenPayload(sub=hid, role=role))
        return LoginResponse(
            success=True, token=token, role=role,
            display_name=display, nickname=nick,
            hospital_id=hid, message="登录成功",
        )

    # 孕妇账号：从数据库查找 hospital_id
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(Pregnant.hospital_id == hid).first()
        if not pregnant:
            return LoginResponse(success=False, message="账号不存在")
        if not verify_password(pwd, _HASH_PREGNANT):
            return LoginResponse(success=False, message="密码错误")
        token = create_token(TokenPayload(sub=hid, role="pregnant", pregnant_id=pregnant.pregnant_id))
        return LoginResponse(
            success=True, token=token, role="pregnant",
            pregnant_id=pregnant.pregnant_id,
            display_name=pregnant.display_name,
            nickname=pregnant.nickname or pregnant.display_name,
            hospital_id=hid, message="登录成功",
        )
    finally:
        db.close()


@router.get("/me")
def get_me(user: TokenPayload = Depends(get_current_user)):
    """获取当前登录用户信息（需要token）"""
    return {"role": user.role, "sub": user.sub, "pregnant_id": user.pregnant_id}


@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """主动注销，将 token 加入黑名单。"""
    from app.core.auth import revoke_token
    revoke_token(credentials.credentials)
    return {"message": "已注销"}
