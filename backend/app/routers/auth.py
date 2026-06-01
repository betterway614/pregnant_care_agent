"""认证 API - JWT + bcrypt"""
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..database import SessionLocal
from ..models import Pregnant
from ..core.auth import (
    hash_password, verify_password, create_token,
    TokenPayload, get_current_user,
)

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])

_PWD_PREGNANT = os.getenv("DEMO_PASSWORD_PREGNANT", "123456")
_PWD_NURSE = os.getenv("DEMO_PASSWORD_NURSE", "nurse123")
_PWD_DOCTOR = os.getenv("DEMO_PASSWORD_DOCTOR", "doctor123")
_PWD_ADMIN = os.getenv("DEMO_PASSWORD_ADMIN", "admin123")

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
def login(req: LoginRequest):
    """登录：医院ID + 密码，返回JWT token"""
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
