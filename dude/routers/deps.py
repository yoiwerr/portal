"""
FastAPI 依赖注入 — JWT 验证。

Go Admin 签发 JWT，Python 用共享 secret 自验。
两个服务不互相调用，只共享 JWT_SECRET 和数据库。
"""

import os
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Shared JWT secret with Go Admin
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be configured with at least 32 characters")
JWT_ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)


class UserClaims:
    """从 JWT 解析出的用户身份。"""
    def __init__(self, user_id: str, username: str, role: str):
        self.user_id = user_id
        self.username = username
        self.role = role


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[UserClaims]:
    """
    验证 JWT 并返回用户身份。
    如果无 token 或 token 无效，返回 None（端点自行决定是否拒绝）。
    """
    if credentials is None:
        return None

    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return UserClaims(
            user_id=payload.get("user_id", ""),
            username=payload.get("username", ""),
            role=payload.get("role", "user"),
        )
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


async def require_user(
    user: Optional[UserClaims] = Depends(get_current_user),
) -> UserClaims:
    """需要登录，否则 401。"""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
