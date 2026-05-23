"""LLM客户端抽象层 - 支持云端/本地双模式切换"""
import os
import json
import re
import httpx
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional
from ..services.followup_service import followup_service


class LLMClient(ABC):
    """大模型调用抽象基类"""

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        ...

    @abstractmethod
    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        ...

    @abstractmethod
    async def chat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """支持工具调用的对话，返回 {role, content, tool_calls}"""
        ...


class CloudAPIClient(LLMClient):
    """开发阶段：云端API (兼容 OpenAI 接口)"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        # 统一 HTTP 客户端超时：连接 15s，读取 120s（LLM 生成需要时间）
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=15.0, read=120.0)
        )
        self._logger = __import__("loguru").logger

    @staticmethod
    def _fix_roles(messages: list[dict]) -> list[dict]:
        """OpenAI SDK v2 可能把 'system' 转成 'developer'，但 Qwen API 不接受 'developer'"""
        fixed = []
        for m in messages:
            if m.get("role") == "developer":
                m = {**m, "role": "system"}
            fixed.append(m)
        return fixed

    def _build_client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=self.http_client,
        )

    async def chat(self, messages: list[dict], **kwargs) -> str:
        client = self._build_client()
        self._logger.info("LLM chat 开始 model={}", self.model)
        import time
        t0 = time.time()
        try:
            resp = await client.chat.completions.create(
                model=self.model,
                messages=self._fix_roles(messages),
                **kwargs
            )
            elapsed = time.time() - t0
            self._logger.info("LLM chat 完成 ({:.1f}s)", elapsed)
            return resp.choices[0].message.content or ""
        except Exception as e:
            elapsed = time.time() - t0
            self._logger.warning("LLM chat 失败 ({:.1f}s): {}", elapsed, e)
            raise

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        client = self._build_client()
        self._logger.info("LLM chat_stream 开始 model={}", self.model)
        try:
            stream = await client.chat.completions.create(
                model=self.model,
                messages=self._fix_roles(messages),
                stream=True,
                **kwargs
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            self._logger.info("LLM chat_stream 完成")
        except Exception as e:
            self._logger.warning("LLM chat_stream 失败: {}", e)
            raise

    async def chat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """使用 OpenAI 原生 function calling"""
        client = self._build_client()
        self._logger.info("LLM chat_with_tools 开始 model={}", self.model)
        import time
        t0 = time.time()
        try:
            resp = await client.chat.completions.create(
                model=self.model,
                messages=self._fix_roles(messages),
                tools=tools,
                tool_choice="auto",
                **kwargs
            )
            elapsed = time.time() - t0
            self._logger.info("LLM chat_with_tools 完成 ({:.1f}s)", elapsed)
            choice = resp.choices[0]
            msg = choice.message
            result = {"role": "assistant", "content": msg.content or "", "tool_calls": None}
            if msg.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            return result
        except Exception as e:
            elapsed = time.time() - t0
            self._logger.warning("LLM chat_with_tools 失败 ({:.1f}s): {}", elapsed, e)
            raise


class LocalOllamaClient(LLMClient):
    """竞赛阶段：本地GPU Ollama推理"""

    def __init__(self, host: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.host = host.rstrip("/")
        self.model = model

    async def chat(self, messages: list[dict], **kwargs) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.host}/api/chat", json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": kwargs.get("max_tokens", 2048)}
            })
            return resp.json()["message"]["content"]

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{self.host}/api/chat", json={
                "model": self.model,
                "messages": messages,
                "stream": True,
                "options": {"num_predict": kwargs.get("max_tokens", 2048)}
            }) as resp:
                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if data.get("message", {}).get("content"):
                                yield data["message"]["content"]
                        except json.JSONDecodeError:
                            continue

    async def chat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """使用 Ollama tools API"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": kwargs.get("max_tokens", 2048)},
        }
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.host}/api/chat", json=payload)
            data = resp.json()
            msg = data.get("message", {})
            result = {"role": "assistant", "content": msg.get("content", ""), "tool_calls": None}
            if "tool_calls" in msg:
                result["tool_calls"] = msg["tool_calls"]
            return result


class MockLLMClient(LLMClient):
    """纯Mock客户端 - 无需任何外部依赖"""

    def __init__(self):
        self.responses = {
            "greeting": "您好呀！我是小安，您的孕期智能助手。今天感觉怎么样？有什么我可以帮您的吗？🌸",
            "weight": "已记录您的体重数据啦！记得保持均衡饮食和适当运动哦。如果体重变化较大，建议咨询医生。",
            "bp": "已记录您的血压数据。请继续保持监测，若收缩压持续≥140或舒张压持续≥90，请及时联系医生。",
            "anxiety": "我理解您现在的感受。孕期情绪波动是很正常的，让我们一起做个简单的呼吸练习好吗？\n\n🌬️ 深吸气... 1、2、3、4\n🌬️ 屏住呼吸... 1、2、3、4\n🌬️ 缓慢呼气... 1、2、3、4\n\n感觉有没有好一点呢？记住，您不是一个人在面对这些。",
            "fetal_movement": "胎动监测非常重要！请每天固定时间（建议饭后1小时）数胎动。正常每小时3-5次。如果发现胎动明显减少或消失，请立即就医。",
            "default": "收到您的消息啦。小安正在认真学习产科知识，希望能给您更准确的回答。如果您有具体问题，请告诉我，我会尽力帮您解答！",
            "emergency": "⚠️ 您描述的情况需要立即就医！请立刻联系您的医生或前往最近医院。如果情况紧急，请拨打120急救电话！",
            "suicide": "⚠️ 我们非常关心您的安全。请立即拨打心理援助热线：400-161-9995，或前往最近医院急诊科寻求帮助。您不是一个人在面对困难。",
        }
        # 随访状态机会话存储
        self._followup_sessions: dict[str, dict] = {}

    async def chat(self, messages: list[dict], **kwargs) -> str:
        content = messages[-1]["content"] if messages else ""
        return self._match_response(content)

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        content = messages[-1]["content"] if messages else ""
        resp = self._match_response(content)
        for chunk in resp:
            yield chunk

    async def chat_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> dict:
        """模拟工具调用：检测随访模式，用状态机推进"""
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        rid_match = re.search(r"随访记录ID[=:]\s*(\S+)", system)
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

        if not rid_match:
            reply = self._match_response(user_msg) if user_msg else self.responses["greeting"]
            return {"role": "assistant", "content": reply, "tool_calls": None}

        record_id = rid_match.group(1)
        session = self._get_or_init_session(record_id, system)
        return self._advance_mock_followup(session, user_msg, messages)

    # ==================== 随访状态机 ====================

    def _get_or_init_session(self, record_id: str, system_prompt: str) -> dict:
        if record_id in self._followup_sessions:
            return self._followup_sessions[record_id]

        tmpl_match = re.search(r"template_name[=:]\s*(\S+)", system_prompt)
        tmpl_id = tmpl_match.group(1) if tmpl_match else "standard"
        template = followup_service.get_template(tmpl_id)
        questions = template["questions"]

        # 从 system prompt 提取健康教育内容
        edu_match = re.search(r'【健康教育内容】\n(.*?)(?:\n\n|\Z)', system_prompt, re.DOTALL)
        health_edu = []
        if edu_match:
            health_edu = [line.strip("- ").strip() for line in edu_match.group(1).strip().split("\n") if line.strip() and line.strip() != "无"]

        name = "准妈妈"
        name_match = re.search(r"孕妇[：:]?\s*([^\n]+)", system_prompt)
        if name_match:
            name = name_match.group(1).strip()

        session = {
            "record_id": record_id,
            "phase": "init",
            "questions": questions,
            "question_index": 0,
            "answers": {},
            "template_id": tmpl_id,
            "patient_name": name,
            "last_answer_key": None,
            "last_answer_value": "",
            "health_education": health_edu,
        }
        self._followup_sessions[record_id] = session
        return session

    def _advance_mock_followup(self, session: dict, user_msg: str, messages: list) -> dict:
        """推进随访状态机：判断是"该提问"还是"该记录回答"，用温暖语气包裹"""
        record_id = session["record_id"]
        name = session.get("patient_name", "准妈妈")

        # 判断最近一条非 system/assistant 消息的角色
        last_role = None
        for m in reversed(messages):
            if m["role"] in ("user", "tool"):
                last_role = m["role"]
                break

        # ---- 阶段1：初始化，获取随访上下文 ----
        if session["phase"] == "init":
            session["phase"] = "answering"
            return self._make_tool_call(
                record_id,
                "get_followup_context",
                {"record_id": record_id},
                f"{name}，您好呀~💗 小安看到您有一个随访提醒，让我先查一下今天的随访内容，马上回来和您聊聊！",
            )

        # ---- 阶段2：回答/提问循环 ----
        if session["phase"] == "answering":
            idx = session["question_index"]
            questions = session["questions"]
            prev_key = session.get("last_answer_key")

            if last_role == "tool":
                # 刚执行完工具 → 需要向孕妇提问（或完成）
                if idx >= len(questions):
                    session["phase"] = "done"
                    return self._make_tool_call(
                        record_id,
                        "complete_followup",
                        {"record_id": record_id, "summary": f"完成随访，共回答{len(session['answers'])}个问题"},
                        f"太棒了，所有问题都问完啦！我来为您归档本次随访记录~ 🎉",
                    )

                # 用温暖语气问下一个问题
                next_q = questions[idx]
                return {
                    "role": "assistant",
                    "content": self._warm_question(name, next_q, idx, len(questions), prev_key, session.get("last_answer_value", "")),
                    "tool_calls": None,
                }

            # last_role == "user"：孕妇回复了 → 记录回答
            if idx < len(questions):
                current_q = questions[idx]
                session["answers"][current_q["key"]] = user_msg
                session["last_answer_key"] = current_q["key"]
                session["last_answer_value"] = user_msg
                session["question_index"] = idx + 1

                return self._make_tool_call(
                    record_id,
                    "record_answer",
                    {
                        "record_id": record_id,
                        "question_key": current_q["key"],
                        "answer_text": user_msg,
                    },
                    "",  # content 空，tool 执行后下轮循环会返回温暖提问
                )

        # ---- 阶段3：完成 ----
        if session["phase"] == "done":
            health_edu = session.get("health_education", [])
            edu_text = ""
            if health_edu:
                edu_text = "\n\n💝 温馨小提示给到您：\n" + "\n".join(f"• {item}" for item in health_edu[:3])
            return {
                "role": "assistant",
                "content": f"随访已完成归档啦！🎉 {name}，感谢您的耐心配合，真棒！"
                           f"如果平时有任何不舒服或疑问，随时可以来找小安聊天哦~"
                           f"祝您和宝宝都健健康康的！💕{edu_text}",
                "tool_calls": None,
            }

        return {"role": "assistant", "content": self.responses["default"], "tool_calls": None}

    def _warm_question(self, name: str, question: dict, idx: int, total: int,
                       prev_key: str | None, prev_value: str) -> str:
        """用温暖的语气包裹问题"""
        q_key = question["key"]
        q_text = question["question"]

        # 第一个问题：温暖开场
        if idx == 0:
            openers = [
                f"{name}，您好呀~💗 今天小安来做温馨随访啦！先问您第一个问题哦：{q_text}",
                f"亲爱的{name}，下午好呀~☀️ 小安来和您聊聊近况！首先想问一下：{q_text}",
                f"{name}您好~🌷 又到了咱们的随访时间啦！让小安先关心一下：{q_text}",
            ]
            return openers[idx % len(openers)]

        # 后续问题：先温暖回应上一个回答，再问下一个
        acknowledgment = self._acknowledge_answer(prev_key, prev_value)

        transitions = {
            "weight": f" 那再问一个关于体重的小问题哦：",
            "bp": f" 再来说说血压方面吧~",
            "fetal_movement": f" 接下来聊聊宝宝的动态~",
            "diet": f" 最后想了解一下您的生活习惯：",
            "feeling": f" 接着想问一下身体状况方面：",
            "medication": f" 还有一个用药方面的问题想确认一下：",
            "wound": f" 再看看伤口恢复的情况：",
        }
        transition = transitions.get(q_key, " 那再问您一个问题：")

        return f"{acknowledgment}{transition}{q_text}"

    def _acknowledge_answer(self, key: str | None, value: str) -> str:
        """根据上一个回答生成温暖的回应"""
        if not key:
            return ""

        acks = {
            "feeling": [
                f"嗯嗯，收到啦！{'听您这么说我就放心啦~😊' if '不' in value or '好' in value or '没' in value else '孕期有些小不适很正常的，您辛苦了~🥺'} ",
                f"明白了，谢谢您告诉我这些~💗 ",
            ],
            "weight": [
                f"好的，已经帮您记下体重数据啦！{'控制得挺不错的呢，继续保持哦~👏' if any(c.isdigit() for c in value) else ''} ",
                f"收到~体重数据很重要，您坚持记录真棒！📝 ",
            ],
            "bp": [
                f"血压已记录好啦！您坚持测量血压的习惯真好，为您点赞~👍 ",
                f"收到血压数据！定期监测真的非常重要呢~💪 ",
            ],
            "fetal_movement": [
                f"了解到宝宝的情况了，谢谢您细心观察！👶💕 ",
                f"胎动数据收到~有在认真数胎动，您真棒！🌟 ",
            ],
            "diet": [
                f"嗯嗯，饮食和睡眠都很重要呢，您的反馈小安记下啦~🌙 ",
                f"谢谢您的分享！好的生活习惯是给宝宝最好的礼物呢~🎁 ",
            ],
            "medication": [
                f"收到，按时用药非常关键，您做得很棒！💊 ",
            ],
            "wound": [
                f"伤口恢复情况了解了，谢谢您的反馈~🩹 ",
            ],
        }

        options = acks.get(key, ["了解啦，谢谢您~💗 "])
        return options[hash(value) % len(options)]

    def _make_tool_call(self, record_id: str, name: str, arguments: dict, content: str = "") -> dict:
        """构造模拟的工具调用返回"""
        return {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": f"call_{name[:4]}_{record_id[-6:]}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(arguments),
                    },
                }
            ],
        }

    def _match_response(self, content: str) -> str:
        keywords = {
            "自杀": "suicide", "不想活": "suicide", "想死": "suicide",
            "大出血": "emergency", "剧烈腹痛": "emergency", "急诊": "emergency",
            "体重": "weight", "血压": "bp", "胎动": "fetal_movement",
            "焦虑": "anxiety", "紧张": "anxiety", "害怕": "anxiety",
            "你好": "greeting", "您好": "greeting",
        }
        for kw, key in keywords.items():
            if kw in content:
                return self.responses[key]

        # NLU健康数据上报
        import re
        weight_match = re.search(r"(\d+\.?\d*)\s*kg", content)
        if weight_match:
            return f"已记录您的体重：{weight_match.group(1)}kg。数据已同步至您的健康档案。"
        bp_match = re.search(r"(\d+)/(\d+)", content)
        if bp_match:
            return f"已记录您的血压：{bp_match.group(1)}/{bp_match.group(2)}mmHg。请继续保持定期监测。"

        return self.responses["default"]


_llm_client_instance: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """工厂函数，通过配置切换LLM客户端（懒加载 + 缓存）"""
    global _llm_client_instance
    if _llm_client_instance is not None:
        return _llm_client_instance

    from ..config import settings

    mode = settings.llm_mode
    if mode == "cloud":
        _llm_client_instance = CloudAPIClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    elif mode == "local":
        # vLLM/SGLang 等 OpenAI 兼容端点优先
        if settings.local_base_url:
            _llm_client_instance = CloudAPIClient(
                api_key="not-needed",
                base_url=settings.local_base_url,
                model=settings.local_model,
            )
        else:
            _llm_client_instance = LocalOllamaClient(
                host=settings.ollama_host,
                model=settings.local_model,
            )
    else:
        _llm_client_instance = MockLLMClient()
    return _llm_client_instance


_pregnant_llm_client_instance: LLMClient | None = None


def get_pregnant_llm_client() -> LLMClient:
    """获取孕妇对话专用的LLM客户端（mixed模式下使用）"""
    global _pregnant_llm_client_instance
    if _pregnant_llm_client_instance is not None:
        return _pregnant_llm_client_instance

    from ..config import settings

    if settings.llm_mode == "mixed":
        mode = settings.llm_pregnant_mode
    else:
        mode = settings.llm_mode

    if mode == "cloud":
        _pregnant_llm_client_instance = CloudAPIClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    elif mode == "local":
        if settings.local_base_url:
            _pregnant_llm_client_instance = CloudAPIClient(
                api_key="not-needed",
                base_url=settings.local_base_url,
                model=settings.local_model,
            )
        else:
            _pregnant_llm_client_instance = LocalOllamaClient(
                host=settings.ollama_host,
                model=settings.local_model,
            )
    else:
        _pregnant_llm_client_instance = MockLLMClient()
    return _pregnant_llm_client_instance


def reset_llm_client():
    """重置LLM客户端（配置变更后调用）"""
    global _llm_client_instance, _pregnant_llm_client_instance
    _llm_client_instance = None
    _pregnant_llm_client_instance = None
