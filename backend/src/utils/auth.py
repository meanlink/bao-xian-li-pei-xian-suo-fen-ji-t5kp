from datetime import datetime, timedelta, timezone
import hashlib
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from src.config import JWT_ALGORITHM, JWT_SECRET
from src.utils.db import get_conn

bearer = HTTPBearer(auto_error=False)

def password_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def create_token(user: dict) -> str:
    payload = {"sub": str(user["id"]), "username": user["username"], "role": user["role"], "display_name": user["display_name"], "exp": datetime.now(timezone.utc) + timedelta(hours=8)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登录")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="登录已过期") from exc
    with get_conn() as conn:
        user = conn.execute("SELECT id, username, role, display_name FROM users WHERE id=%s", (int(payload["sub"]),)).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return dict(user)

def require_roles(*roles):
    def dependency(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="当前角色无权执行此操作")
        return user
    return dependency
