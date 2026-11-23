from fastapi import APIRouter, HTTPException
from src.schemas.auth import LoginRequest
from src.utils.auth import password_hash, create_token
from src.utils.db import get_conn

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(payload: LoginRequest):
    with get_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=%s AND password_hash=%s", (payload.username, password_hash(payload.password))).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return {"token": create_token(user), "user": {"id": user["id"], "username": user["username"], "role": user["role"], "display_name": user["display_name"]}}
