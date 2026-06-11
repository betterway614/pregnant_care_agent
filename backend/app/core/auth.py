"""JWT认证工具"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _get_or_create_secret_key() -> str:
    """获取 JWT Secret Key，优先从环境变量读取，否则持久化到文件。

    解决每次进程重启 secret_key 变化导致所有已签发 token 失效的问题。
    多 worker 部署时必须通过环境变量 JWT_SECRET_KEY 统一设置。
    """
    env_key = os.getenv("JWT_SECRET_KEY")
    if env_key:
        return env_key

    # 尝试从文件读取已持久化的 key
    key_file = os.path.join(os.path.dirname(__file__), "..", ".jwt_secret")
    key_file = os.path.abspath(key_file)
    try:
        if os.path.exists(key_file):
            with open(key_file, "r") as f:
                key = f.read().strip()
                if len(key) >= 32:
                    return key
    except OSError:
        pass

    # 生成新 key 并持久化
    new_key = os.urandom(32).hex()
    try:
        with open(key_file, "w") as f:
            f.write(new_key)
        os.chmod(key_file, 0o600)
        logger.warning("JWT_SECRET_KEY 未设置，已生成并持久化到 %s。生产环境请设置环境变量。", key_file)
    except OSError as e:
        logger.warning("无法持久化 JWT Secret Key (%s)，每次重启 token 将失效。", e)
    return new_key


SECRET_KEY = _get_or_create_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# Token 撤销黑名单（内存存储，容器重启后清空）
_revoked_tokens: set[str] = set()

def revoke_token(token: str) -> None:
    """将 token 加入撤销列表。"""
    _revoked_tokens.add(token)

def is_token_revoked(token: str) -> bool:
    """检查 token 是否已被撤销。"""
    return token in _revoked_tokens


class TokenPayload(BaseModel):
    sub: str
    role: str
    pregnant_id: str = ""


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(payload: TokenPayload) -> str:
    data = payload.model_dump()
    data["exp"] = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[TokenPayload]:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        payload = TokenPayload(**data)
    except JWTError:
        return None
    # 检查 token 是否已被撤销
    if is_token_revoked(token):
        return None
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证凭据")
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证凭据无效或已过期")
    return payload


def extract_user_from_header(authorization: str | None) -> TokenPayload | None:
    """从 Authorization 头提取用户信息（非 FastAPI 依赖注入方式）

    用于未添加 Depends(get_current_user) 的端点中，
    尝试从请求头中提取当前用户，失败返回 None。
    """
    if not authorization:
        return None
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            return None
        return decode_token(token)
    except (ValueError, AttributeError):
        return None
