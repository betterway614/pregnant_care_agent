"""简易认证 API - Demo用"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..database import SessionLocal
from ..models import Pregnant

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


class LoginRequest(BaseModel):
    hospital_id: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    role: str = ""
    pregnant_id: str = ""
    display_name: str = ""
    nickname: str = ""
    hospital_id: str = ""
    message: str = ""


MOCK_PASSWORDS = {
    "pregnant": "123456",
    "nurse": "nurse123",
    "doctor": "doctor123",
}


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """简易登录：医院ID + 密码"""
    hid = req.hospital_id.strip()
    pwd = req.password.strip()

    # 护士/医生管理员账号
    if hid == "nurse" and pwd == MOCK_PASSWORDS["nurse"]:
        return LoginResponse(
            success=True, role="nurse",
            pregnant_id="", display_name="护士长", nickname="小护",
            hospital_id=hid, message="登录成功"
        )
    if hid == "doctor" and pwd == MOCK_PASSWORDS["doctor"]:
        return LoginResponse(
            success=True, role="doctor",
            pregnant_id="", display_name="主任医师", nickname="Dr.智",
            hospital_id=hid, message="登录成功"
        )

    # 孕妇登录：匹配mock数据中的hospital_id
    db = SessionLocal()
    try:
        pregnant = db.query(Pregnant).filter(
            Pregnant.hospital_id == hid
        ).first()

        if not pregnant:
            return LoginResponse(
                success=False, message="账号不存在，请检查医院ID卡号"
            )

        if pwd != MOCK_PASSWORDS["pregnant"]:
            return LoginResponse(
                success=False, message="密码错误，请重试（Demo默认密码：123456）"
            )

        return LoginResponse(
            success=True, role="pregnant",
            pregnant_id=pregnant.pregnant_id,
            display_name=pregnant.display_name,
            nickname=pregnant.nickname or pregnant.display_name,
            hospital_id=hid,
            message="登录成功"
        )
    finally:
        db.close()
