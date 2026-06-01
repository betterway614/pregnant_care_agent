# AI-Care 竞赛评审改进计划（修订版）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根据评审团62.5/100的评分，修复关键缺陷，目标提升至75-80分

**Architecture:** 按P0(安全合规)→P1(核心能力)→P2(竞争力)优先级分3阶段实施，每阶段独立可验证

**Tech Stack:** FastAPI, JWT (python-jose), bcrypt (passlib), regex, ONNX Runtime

**评审维度权重:** 技术创新25% | 行业价值25% | 性能效率20% | 隐私合规15% | Agent架构15%

---

## 阶段 P0: 安全合规修复（预计1.5天，隐私合规 6→12分）

### Task 1: JWT认证 + 保留前端便捷登录

**设计原则:** 后端API必须有JWT保护（评审看代码），前端保留admin快捷登录（演示方便）。
快捷登录改为调用后端API获取token，而非纯前端绕过。

**Files:**
- Create: `backend/app/core/auth.py`
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/views/Login.vue`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: 安装依赖**

```bash
cd backend
pip install python-jose[cryptography] passlib[bcrypt]
echo 'python-jose[cryptography]>=3.3.0' >> requirements.txt
echo 'passlib[bcrypt]>=1.7.4' >> requirements.txt
```

- [ ] **Step 2: 创建 `backend/app/core/auth.py`**

```python
"""JWT认证工具"""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.urandom(32).hex())
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


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
        return TokenPayload(**data)
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证凭据")
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证凭据无效或已过期")
    return payload
```

- [ ] **Step 3: 重写 `backend/app/routers/auth.py`**

```python
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

# 密码从环境变量读取，启动时bcrypt哈希
_PWD_PREGNANT = os.getenv("DEMO_PASSWORD_PREGNANT", "123456")
_PWD_NURSE = os.getenv("DEMO_PASSWORD_NURSE", "nurse123")
_PWD_DOCTOR = os.getenv("DEMO_PASSWORD_DOCTOR", "doctor123")
_PWD_ADMIN = os.getenv("DEMO_PASSWORD_ADMIN", "admin123")

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
    hid = req.hospital_id.strip()
    pwd = req.password.strip()
    if not hid or not pwd:
        return LoginResponse(success=False, message="请输入账号和密码")

    # 固定账号
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

    # 孕妇登录
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
    return {"role": user.role, "sub": user.sub, "pregnant_id": user.pregnant_id}
```

- [ ] **Step 4: 在 `main.py` 添加认证中间件**

在 CORS 配置之后添加:

```python
PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc",
                "/api/v1/auth/login"}

@app.middleware("http")
async def auth_middleware(request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or request.method == "OPTIONS":
        return await call_next(request)
    if path.startswith("/assets") or path.endswith((".js", ".css", ".ico")):
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "未提供认证凭据"})
    from .core.auth import decode_token
    payload = decode_token(auth[7:])
    if payload is None:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "认证凭据无效或已过期"})
    return await call_next(request)
```

- [ ] **Step 5: 修改 `Login.vue` — 保留快捷登录但走后端API**

admin/nurse/doctor快捷登录保留，但改为调用后端获取token:

```typescript
async function handleLogin() {
  // ... 表单验证 ...

  loggingIn.value = true
  try {
    // 统一走后端API（admin也是）
    const res = await axios.post('/api/v1/auth/login', {
      hospital_id: form.hospital_id.trim(),
      password: form.password.trim(),
    })
    const data = res.data
    if (!data.success) {
      ElMessage.error(data.message || '登录失败')
      return
    }
    // 存储token
    localStorage.setItem('token', data.token)
    appStore.login(data.role === 'pregnant' ? 'pregnant' : data.role as any, data.pregnant_id)
    ElMessage.success(`欢迎，${data.nickname || data.display_name}！`)
    // ... 跳转逻辑不变 ...
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '网络错误')
  } finally {
    loggingIn.value = false
  }
}
```

Demo账号提示保留（评审演示时方便输入）。

- [ ] **Step 6: 修改 `api/client.ts` 添加token拦截器**

```typescript
// 请求拦截器：自动携带token
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401跳转登录
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)
```

- [ ] **Step 7: 测试**

```bash
# 获取token
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"hospital_id":"nurse","password":"nurse123"}' | jq .token

# 无token应401
curl -s http://localhost:8000/api/v1/chat/context/H202501 | jq .

# 有token应200
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"hospital_id":"nurse","password":"nurse123"}' | jq -r .token)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/chat/context/H202501 | jq .
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/auth.py backend/app/routers/auth.py backend/app/main.py \
        frontend/src/views/Login.vue frontend/src/api/client.ts backend/requirements.txt
git commit -m "feat: JWT auth with bcrypt, frontend demo login preserved"
```

---

### Task 2: 移除硬编码密钥

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: 修改 `config.py`**

```python
# 修改前:
asr_cloud_api_key: str = "sk-54b8481fe3a648ccb3bb8d20126420c2"
tts_cloud_api_key: str = "sk-54b8481fe3a648ccb3bb8d20126420c2"

# 修改后:
asr_cloud_api_key: str = ""
tts_cloud_api_key: str = ""
```

- [ ] **Step 2: 更新 `.env.example`**

```env
ASR_CLOUD_API_KEY=your_dashscope_key_here
TTS_CLOUD_API_KEY=your_dashscope_key_here
JWT_SECRET_KEY=generate_with_openssl_rand_hex_32
```

- [ ] **Step 3: 确认 `.env` 在 `.gitignore` 中**

```bash
grep -q "^\.env$" .gitignore || echo ".env" >> .gitignore
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py backend/.env.example .gitignore
git commit -m "fix: remove hardcoded API keys from source code"
```

---

### Task 3: UI合规声明 + CORS收紧

**Files:**
- Modify: `frontend/src/views/Login.vue`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 在 `Login.vue` 添加合规声明**

在 `login-hint` div 之后:

```vue
<div class="compliance-notice">
  <el-icon><Warning /></el-icon>
  <span>本系统仅用于科研教学辅助，不替代临床诊断。所有AI分析结果需经医生审核确认。</span>
</div>
```

```css
.compliance-notice {
  margin-top: 16px;
  padding: 10px 14px;
  background: #FFF3E0;
  border: 1px solid #FFE0B2;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: #E65100;
  display: flex;
  align-items: center;
  gap: 8px;
  line-height: 1.5;
}
```

- [ ] **Step 2: 收紧CORS**

```python
# main.py - 修改前:
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# 修改后:
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, ...)
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/Login.vue backend/app/main.py
git commit -m "feat: add compliance disclaimer and restrict CORS"
```

---

## 阶段 P1: 核心能力提升（预计7天，技术+性能+行业价值）

### Task 4: NLU正则模式扩充（仅规则层，不加LLM）

**设计决策:** LLM回退分类器暂不实现，待Agent架构讨论后再定。
仅扩充正则覆盖更多口语化表达，解决"宝宝动得少了"这类漏匹配。

**Files:**
- Modify: `backend/app/core/nlu_engine.py`
- Modify: `backend/app/core/agno_tools.py`
- Create: `backend/tests/test_nlu_expanded.py`

- [ ] **Step 1: 扩充 `INTENT_PATTERNS`**

在 `nlu_engine.py` 中:

```python
INTENT_PATTERNS = {
    "HEALTH_DATA_REPORT": [
        r"(体重|血压|胎动|血糖|心率).*?(\d+)",
        r"(\d+\.?\d*)\s*(kg|斤|mmHg|次)",
        r"(记录|上报|提交|输入).*?(体重|血压|血糖|胎动)",
        r"(今天|刚才|刚刚).*?(称了|量了|测了)",
    ],
    "EMOTION_EXPRESS": [
        r"(焦虑|紧张|害怕|担心|抑郁|难过|失眠|压力)",
        r"(不开心|好烦|睡不着|很累)",
        r"(宝宝.*?动.*?(少|没|不怎么))",
        r"(感觉.*?(不对|不好|有问题|不舒服))",
        r"(心情.*?(差|不好|低落))",
    ],
    "KNOWLEDGE_QUERY": [
        r"(什么|怎么|为什么|能否|可以|需要|应该)",
        r"(饮食|运动|睡觉|吃药|检查|注意事项)",
        r"(能不能|可不可以|要不要|有没有影响)",
        r"(正常.*?(范围|值|标准))",
    ],
    "SCHEDULE_INQUIRY": [
        r"(产检|检查|预约|什么时候|提醒)",
        r"(下次|这周|下周).*?(去|来|做).*?(检查|产检)",
    ],
    "EMERGENCY": [
        r"(大出血|剧烈腹痛|昏倒|昏迷|呼吸困难|休克)",
        r"(急诊|120|救护车)",
        r"(出血.*?(多|不止|很多))",
        r"(肚子.*?(剧痛|绞痛|一阵一阵.*?痛))",
    ],
    "GREETING": [
        r"^(你好|您好|嗨|hi|hello|早上好|下午好|晚上好)",
    ],
}
```

- [ ] **Step 2: 更新 `INTENT_TO_GROUP` 映射**

在 `agno_tools.py` 中添加:

```python
INTENT_TO_GROUP: dict[str, str] = {
    # ... 现有映射 ...
    "health_data_report": "record",  # NLU返回HEALTH_DATA_REPORT的大写映射
    "schedule_inquiry": "qa",         # 产检排期问题走知识问答
}
```

注意: `resolve_tools_by_intent` 中 `intent = nlu_result.get("intent", "").lower()` 会将
`HEALTH_DATA_REPORT` 转为 `health_data_report`，需确保映射匹配。

- [ ] **Step 3: 编写测试**

```python
# backend/tests/test_nlu_expanded.py
from app.core.nlu_engine import nlu_engine

def test_natural_fetal_movement():
    result = nlu_engine.parse("我最近感觉宝宝动得少了")
    assert result.intent != "UNKNOWN"

def test_vague_discomfort():
    result = nlu_engine.parse("感觉今天有点不对劲")
    assert result.intent != "UNKNOWN"

def test_emergency_still_works():
    result = nlu_engine.parse("大出血了怎么办")
    assert result.is_emergency is True

def test_numeric_data():
    result = nlu_engine.parse("今天血压130/85")
    assert result.intent == "HEALTH_DATA_REPORT"
    assert result.entities.get("sbp") == 130.0
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/nlu_engine.py backend/app/core/agno_tools.py backend/tests/test_nlu_expanded.py
git commit -m "feat: expand NLU regex patterns for natural language coverage"
```

---

### Task 5: Guardrail正则升级（否定感知）

**Files:**
- Modify: `backend/app/core/agno_guardrails.py`

- [ ] **Step 1: 将子串匹配改为正则**

```python
import re

class MedicalSafetyGuardrail:
    __name__ = "MedicalSafetyGuardrail"

    BLOCKED_PATTERNS = [
        re.compile(r"(?<!不是)(?<!并非)(?<!无法)(?<!排除.{0,4})诊断为"),
        re.compile(r"(?<!不是)(?<!并非)确诊"),
        re.compile(r"建议用药|建议服用|处方(?!签)"),
        re.compile(r"可以吃药|应该吃药|用药方案"),
    ]

    def check(self, response: str) -> Optional[str]:
        if not response:
            return None
        for pattern in self.BLOCKED_PATTERNS:
            if pattern.search(response):
                return "小安不能提供诊断或用药建议。请咨询医生获取专业意见。"
        return None


class DoctorDraftGuardrail:
    __name__ = "DoctorDraftGuardrail"

    BLOCKED_PATTERNS = [
        re.compile(r"(?<!不是)(?<!并非)(?<!无法)(?<!排除.{0,4})确诊"),
        re.compile(r"(?<!不是)(?<!并非)确定诊断|明确诊断"),
        re.compile(r"无需进一步检查|无需进一步评估"),
        re.compile(r"(?<!不是)没有风险|完全正常"),
        re.compile(r"(?<!不是)(?<!并非)(?<!无法)(?<!排除.{0,4})诊断为|诊断是"),
        re.compile(r"可以排除(?!.{0,4}的可能性)"),
        re.compile(r"治疗方案(为|确定)(?!.{0,4}的建议)"),
    ]

    def check(self, response: str) -> Optional[str]:
        if not response:
            return None
        for pattern in self.BLOCKED_PATTERNS:
            if pattern.search(response):
                return "以上分析为AI辅助生成，不构成确定性诊断结论，需医生审核确认。"
        return None


def check_output_safety(text: str, patterns: list) -> Optional[str]:
    if not text:
        return None
    for pattern in patterns:
        if isinstance(pattern, re.Pattern):
            if pattern.search(text):
                return "输出包含受限内容，已拦截"
        else:
            if pattern in text:
                return f"输出包含受限内容（{pattern}），已拦截"
    return None
```

- [ ] **Step 2: 验证**

```bash
cd backend && python -c "
from app.core.agno_guardrails import MedicalSafetyGuardrail
g = MedicalSafetyGuardrail()
assert g.check('虽然不是诊断为子痫前期，但需要关注') is None
assert g.check('无法确诊，建议进一步检查') is None
assert g.check('诊断为子痫前期') is not None
assert g.check('建议用药：拉贝洛尔') is not None
print('Guardrail tests passed')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/agno_guardrails.py
git commit -m "fix: guardrails use regex with negation-aware matching"
```

---

### Task 6: INT8量化执行 + FGR延迟实测

**Files:**
- Create: `backend/scripts/benchmark_fgr.py`

- [ ] **Step 1: 执行INT8量化**

```bash
cd backend
python -m fgr_compete.quantize_onnx
ls fgr_compete/onnx_resnet/*_int8.onnx  # 验证生成
```

- [ ] **Step 2: 创建FGR延迟基准测试**

```python
# backend/scripts/benchmark_fgr.py
"""FGR ONNX推理延迟基准测试（FP32 vs INT8）"""
import time
import numpy as np
from pathlib import Path

def benchmark_fgr():
    from fgr_compete.onnx_predictor import ONNXFGRPredictor
    from fgr_compete.config import ONNX_DIR

    predictor = ONNXFGRPredictor(backend="onnx_cpu")
    predictor.initialize()

    dummy_raw = np.random.randint(0, 255, (256, 256), dtype=np.uint8)
    dummy_mask = np.ones((256, 256), dtype=bool)

    N, WARMUP = 20, 3
    times = []
    for i in range(N + WARMUP):
        t0 = time.perf_counter()
        predictor.predict(dummy_raw, dummy_mask)
        t1 = time.perf_counter()
        if i >= WARMUP:
            times.append(t1 - t0)

    avg = np.mean(times) * 1000
    p50 = np.percentile(times, 50) * 1000
    p95 = np.percentile(times, 95) * 1000
    print(f"FGR ({predictor.model_paths[0].split('/')[-1]}):")
    print(f"  avg={avg:.1f}ms  p50={p50:.1f}ms  p95={p95:.1f}ms  ({N} runs)")
    return avg

if __name__ == "__main__":
    benchmark_fgr()
```

- [ ] **Step 3: 运行并记录**

```bash
cd backend
python scripts/benchmark_fgr.py | tee ../docs/benchmark_logs/fgr_benchmark.txt
```

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/benchmark_fgr.py docs/benchmark_logs/fgr_benchmark.txt
git commit -m "feat: INT8 quantization + FGR latency benchmark"
```

---

### Task 7: 基准测试方法论修复（简化版：3次+warmup）

**Files:**
- Modify: `backend/scripts/benchmark_agent_streaming.py`

- [ ] **Step 1: 添加warmup和3次重复**

在 `run_all` 函数中:

```python
REPEATS = 3
WARMUP_RUNS = 1

async def run_all(all_logs: list) -> dict:
    results = {}
    for tc in TEST_CASES:
        name = tc["name"]
        results[name] = {}
        print(f"\n  {name}")

        for backend, tag, base_url, api_key, model, disable_thinking in [
            ("cloud", "☁️", CLOUD_BASE_URL, CLOUD_API_KEY, CLOUD_MODEL, True),
            ("local", "🖥️", LOCAL_BASE_URL, LOCAL_API_KEY, LOCAL_MODEL, False),
        ]:
            # Warmup
            for _ in range(WARMUP_RUNS):
                try:
                    await stream_call(base_url, api_key, model,
                                      tc["system"], tc["user"], backend,
                                      disable_thinking, all_logs)
                except:
                    pass

            # 正式测试
            runs = []
            for _ in range(REPEATS):
                try:
                    r = await stream_call(base_url, api_key, model,
                                          tc["system"], tc["user"], backend,
                                          disable_thinking, all_logs)
                    runs.append(r)
                except Exception as e:
                    print(f"    {tag} ERROR: {e}")

            if runs:
                import numpy as np
                agg = runs[0].copy()
                agg["latency"] = round(np.mean([r["latency"] for r in runs]), 4)
                agg["ttft"] = round(np.mean([r["ttft"] for r in runs]), 4)
                agg["text_tok_per_sec"] = round(np.mean([r["text_tok_per_sec"] for r in runs]), 2)
                agg["latency_range"] = f"{min(r['latency'] for r in runs):.2f}-{max(r['latency'] for r in runs):.2f}"
                agg["runs"] = len(runs)
                results[name][backend] = agg
                print(f"    {tag} avg:{agg['latency']:.1f}s range:{agg['latency_range']}s ({agg['runs']}runs)")
            else:
                results[name][backend] = {"error": "all runs failed"}

    return results
```

- [ ] **Step 2: Commit**

```bash
git add backend/scripts/benchmark_agent_streaming.py
git commit -m "fix: benchmark - add warmup + 3x repeats + range reporting"
```

---

### Task 8: 知识库扩充（3-5篇）+ 临床指南工具接入RAG

**Files:**
- Create: `backend/knowledge_docs/preeclampsia_guidelines.md`
- Create: `backend/knowledge_docs/gdm_management.md`
- Create: `backend/knowledge_docs/fetal_movement_monitoring.md`
- Modify: `backend/app/core/agno_tools.py`

- [ ] **Step 1: 创建3篇核心知识文档**

每篇200-500字，包含来源标注。主题：
1. 子痫前期识别与管理（ACOG 2023）
2. 妊娠期糖尿病管理（ACOG 2023）
3. 胎动监测指南（RCOG）

- [ ] **Step 2: 重新导入知识库**

```bash
cd backend
python scripts/ingest_knowledge.py
```

- [ ] **Step 3: 将 `agno_query_clinical_guideline` 改为RAG优先**

```python
@tool
def agno_query_clinical_guideline(topic: str = "") -> dict:
    """查询临床指南和规范。优先使用知识库语义检索。"""
    try:
        from .agno_rag import search_knowledge_base
        results = search_knowledge_base(topic, limit=3)
        if results:
            return {
                "topic": topic,
                "guidelines": [r.get("content", "")[:500] for r in results],
                "source": "knowledge_base",
            }
    except Exception:
        pass

    # 回退
    guidelines = {
        "fgr": "ACOG Practice Bulletin No. 204: Fetal Growth Restriction (2021)",
        "gdm": "ACOG Practice Bulletin No. 190: Gestational Diabetes Mellitus (2023)",
        "hypertension": "ACOG Practice Bulletin No. 222: Gestational Hypertension and Preeclampsia (2023)",
        "prenatal": "中华医学会妇产科学分会. 孕前和孕期保健指南(2022)",
    }
    topic_lower = topic.lower()
    matched = [v for k, v in guidelines.items() if k in topic_lower]
    if not matched:
        matched = list(guidelines.values())[:3]
    return {"topic": topic, "guidelines": matched, "source": "hardcoded_fallback"}
```

- [ ] **Step 4: Commit**

```bash
git add backend/knowledge_docs/ backend/app/core/agno_tools.py
git commit -m "feat: expand knowledge base + connect guideline tool to RAG"
```

---

### Task 9: Agent变体差异化prompt

**Files:**
- Modify: `backend/app/core/prompts.py`
- Modify: `backend/app/core/agno_agent.py`

- [ ] **Step 1: 在 `prompts.py` 添加变体指令**

```python
VARIANT_INSTRUCTIONS = {
    "chat": (
        "你是小安，一位温暖亲切的孕期健康助手。\n"
        "当前模式：日常聊天和情绪安抚。\n"
        "用轻松友好的语气交流，关注孕妇的情绪状态。"
    ),
    "record": (
        "你是小安，一位细心的孕期健康记录助手。\n"
        "当前模式：健康数据记录。\n"
        "请确认收到的数据，给出简短评价（是否在正常范围）。"
    ),
    "qa": (
        "你是小安，一位专业的孕期知识顾问。\n"
        "当前模式：知识问答。\n"
        "基于权威指南回答问题，引用来源，使用通俗语言。"
    ),
    "emergency": (
        "你是小安，一位紧急情况响应助手。\n"
        "当前模式：紧急响应。\n"
        "回复极度简洁，只给最关键的行动指令。"
    ),
}
```

- [ ] **Step 2: 修改 `_build_agent` 使用变体指令**

```python
def _build_agent(variant_name: str, tools: list, tool_call_limit: int) -> Agent:
    from .prompts import VARIANT_INSTRUCTIONS, get_pregnant_system_prompt_instructions
    instructions = VARIANT_INSTRUCTIONS.get(variant_name, get_pregnant_system_prompt_instructions())
    return Agent(
        name=f"小安-{variant_name}",
        model=get_agno_model(role="pregnant"),
        instructions=instructions,
        tools=tools,
        # ... 其余不变
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/agno_agent.py backend/app/core/prompts.py
git commit -m "feat: differentiate agent variants with specialized prompts"
```

---

## 阶段 P2: 竞争力提升（预计2天）

### Task 10: 工作流接入主对话路径

**Files:**
- Modify: `backend/app/core/agno_chat_handler.py`

- [ ] **Step 1: 在复杂查询时路由到工作流**

```python
# 在 handle_chat_with_agno 中，NLU分类之后:
if variant == "complex" and intent in ("ASK_SYMPTOM", "ASK_EXAM"):
    try:
        from .agno_workflow import get_prenatal_workflow
        workflow = get_prenatal_workflow()
        workflow.session_state = {"patient_id": pregnant_id, "risk_level": "routine"}
        result = await workflow.arun(message=req.message)
        return result
    except Exception as e:
        logger.warning("工作流执行失败，回退到单Agent: {}", e)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/agno_chat_handler.py
git commit -m "feat: route complex queries through prenatal workflow"
```

---

### Task 11: 功耗实测（条件性）

**说明:** 仅在AMD Ryzen AI硬件可用时执行。无硬件时跳过，在论文/Slides中注明"设计目标"。

**Files:**
- Create: `backend/scripts/measure_power.sh`

- [ ] **Step 1: 创建功耗测量脚本**

```bash
#!/bin/bash
# 用法: bash scripts/measure_power.sh [seconds]
DURATION=${1:-60}
LOG="../docs/benchmark_logs/power_measurement.txt"
echo "=== AI-Care 功耗测量 $(date) ===" > "$LOG"

if command -v rocm-smi &> /dev/null; then
    echo "rocm-smi available, measuring..." | tee -a "$LOG"
    timeout "$DURATION" rocm-smi --showpower --csv >> "$LOG" 2>&1
elif [ -f /sys/class/powercap/intel-rapl:0/energy_uj ]; then
    E1=$(cat /sys/class/powercap/intel-rapl:0/energy_uj)
    sleep "$DURATION"
    E2=$(cat /sys/class/powercap/intel-rapl:0/energy_uj)
    echo "平均功耗: $(( (E2-E1)/1000000/DURATION ))W (${DURATION}s)" | tee -a "$LOG"
else
    echo "无功耗测量接口，请使用外部功率计" | tee -a "$LOG"
fi
```

- [ ] **Step 2: Commit**

```bash
git add backend/scripts/measure_power.sh
git commit -m "feat: add power measurement script (conditional on hardware)"
```

---

## 延迟讨论项（不在本轮实施）

| 项目 | 原因 | 待讨论 |
|------|------|--------|
| NLU LLM回退分类器 | 需与Agent架构整体讨论 | 是否用BERT-tiny on NPU vs LLM API |
| 跨角色共享记忆 | 架构改动大 | Agno原生记忆 vs 自建MemoryManager统一 |
| FGR准确率提升 | 需要更多训练数据 | ImageNet预训练 + 临床特征融合 |
| HIS/EHR集成 | 超出竞赛范围 | FHIR标准接口设计 |
| NMPA合规路径 | 长期工作 | 竞赛后推进 |

---

## 验证检查清单

- [ ] `curl -X POST localhost:8000/api/v1/auth/login` 返回token
- [ ] 无token访问API返回401
- [ ] Login.vue显示合规声明
- [ ] `grep -r "sk-54b8" backend/app/` 返回空
- [ ] `python scripts/benchmark_fgr.py` 输出延迟数据
- [ ] `python scripts/benchmark_agent_streaming.py` 含warmup+3次重复
- [ ] 知识库文档数量 >= 6（原3 + 新增3）
- [ ] `nlu_engine.parse("宝宝动得少了").intent` 不返回UNKNOWN
