# 后端开发记录（认证服务对接草案）

本项目的前端登录流程已就绪（见 mediaclient/lib/README.md）。后端建议使用 FastAPI 0.100.0+，虚拟环境位于 `media-server/venv`，依赖使用 `requirements.txt` 管理。

## 环境配置

```bash
# 进入后端目录
cd media-server

# 创建并激活虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install fastapi==0.115.0 uvicorn[standard]==0.30.0 pydantic==2.9.2

# 保存到 requirements.txt（示例）
pip freeze > requirements.txt
```

## 认证接口草案（带完整类型提示）

```python
from typing import Literal
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Media Server API")

class SendCodeReq(BaseModel):
    phone: str = Field(min_length=11, max_length=11, description="11位手机号")

class SendCodeResp(BaseModel):
    ok: bool
    expire_at: datetime

class VerifyCodeReq(BaseModel):
    phone: str = Field(min_length=11, max_length=11)
    code: str = Field(min_length=6, max_length=6)

class VerifyCodeResp(BaseModel):
    ok: bool
    token_type: Literal["bearer"] = "bearer"
    access_token: str = "demo-token"

@app.post("/api/auth/send_code", response_model=SendCodeResp)
async def send_code(req: SendCodeReq) -> SendCodeResp:
    # TODO: 调用短信服务或实现自发码逻辑
    expire = datetime.utcnow() + timedelta(minutes=10)
    return SendCodeResp(ok=True, expire_at=expire)

@app.post("/api/auth/verify_code", response_model=VerifyCodeResp)
async def verify_code(req: VerifyCodeReq) -> VerifyCodeResp:
    # 示例：验证码固定为 123456
    if req.code != "123456":
        raise HTTPException(status_code=400, detail="验证码错误")
    return VerifyCodeResp(ok=True, access_token="demo-token")
```

启动服务：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 前端对接说明

- `send_code(phone)`: `POST /api/auth/send_code`，前端传入手机号，后端返回过期时间；收到后启动倒计时。
- `verify_code(phone, code)`: `POST /api/auth/verify_code`，返回 `access_token`；前端保存并将登录态切换为已登录。

后续将把前端的 `AuthController` 替换为真实 API 调用，并存储 token 到安全存储（例如 `flutter_secure_storage`）。