"""鉴权核心：JWT（RBAC：supplier / admin）+ 服务级 API Key。

- 供应商(supplier)：通过 SRM 系统登录后拿到的令牌访问问答。
- 管理员(admin)：可管理知识库重建、注册子账号。
- 服务级 API Key：供 SRM 后端 / iframe 直接调用，无需用户登录态。
"""
from __future__ import annotations

import time
import warnings
from typing import List, Optional

from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import User, get_session

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
ALGO = settings.jwt_algorithm


def _secret() -> str:
    if settings.jwt_secret:
        return settings.jwt_secret
    warnings.warn("JWT_SECRET 未设置，使用开发密钥（生产环境请配置强随机值）")
    return "dev-only-insecure-secret-change-me-in-production"


def hash_password(p: str) -> str:
    return pwd_context.hash(p)


def verify_password(p: str, h: str) -> bool:
    if not h:
        return False
    return pwd_context.verify(p, h)


def create_access_token(subject: str, role: str, expires_min: Optional[int] = None) -> str:
    exp = int(time.time()) + (expires_min or settings.access_token_expire_min) * 60
    payload = {"sub": subject, "role": role, "exp": exp}
    return jwt.encode(payload, _secret(), algorithm=ALGO)


def decode_token(token: str) -> dict:
    return jwt.decode(token, _secret(), algorithms=[ALGO])


class Principal:
    def __init__(self, user_id: str, role: str, scope: str = "user"):
        self.user_id = user_id
        self.role = role
        self.scope = scope  # user | service


def get_current_principal(request: Request) -> Principal:
    """支持三种认证方式：Bearer JWT、X-API-Key、查询参数 token（便于 SSE/iframe）。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            data = decode_token(auth[7:].strip())
            return Principal(data.get("sub", "unknown"), data.get("role", "supplier"), "user")
        except JWTError:
            raise HTTPException(status_code=401, detail="无效或过期的令牌")

    api_key = (
        request.headers.get("X-API-Key")
        or request.query_params.get("token")
        or request.query_params.get("api_key")
    )
    if api_key:
        keys = [k.strip() for k in settings.api_keys.split(",") if k.strip()]
        if api_key in keys:
            return Principal("service", "service", "service")
        with get_session() as s:
            u = s.query(User).filter(User.api_key == api_key).first()
            if u:
                return Principal(str(u.id), u.role, "user")
        raise HTTPException(status_code=401, detail="无效的 API Key")

    raise HTTPException(status_code=401, detail="缺少认证凭据")


def require_roles(*roles: str):
    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if roles and principal.role not in roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return principal

    return dependency


def roles_of(principal: Principal) -> List[str]:
    return [principal.role]
