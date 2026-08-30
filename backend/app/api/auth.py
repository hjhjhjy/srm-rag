"""认证接口：登录签发 JWT、当前用户、管理员注册子账号。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    Principal,
    create_access_token,
    get_current_principal,
    hash_password,
    require_roles,
    verify_password,
)
from app.db import User, get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "supplier"


class UserInfo(BaseModel):
    username: str
    role: str


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    with get_session() as s:
        u = s.query(User).filter(User.username == req.username).first()
        if not u or not verify_password(req.password, u.hashed_password):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        token = create_access_token(str(u.id), u.role)
        return TokenResponse(access_token=token, role=u.role)


@router.get("/me", response_model=UserInfo)
def me(principal: Principal = Depends(get_current_principal)):
    return UserInfo(username=principal.user_id, role=principal.role)


@router.post("/register", response_model=UserInfo)
def register(req: RegisterRequest, _: Principal = Depends(require_roles("admin"))):
    if req.role not in ("supplier", "admin"):
        raise HTTPException(status_code=400, detail="role 必须为 supplier 或 admin")
    with get_session() as s:
        if s.query(User).filter(User.username == req.username).first():
            raise HTTPException(status_code=409, detail="用户已存在")
        u = User(username=req.username, hashed_password=hash_password(req.password), role=req.role)
        s.add(u)
        s.commit()
        return UserInfo(username=u.username, role=u.role)
