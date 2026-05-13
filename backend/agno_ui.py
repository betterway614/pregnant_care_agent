"""Agno AgentOS UI 启动脚本

复用 agno_agent.py 和 agno_medical_agents.py 中的 Agent 工厂函数，
确保 AgentOS UI 与主应用使用相同的 Agent 定义。
"""
from agno.os import AgentOS
from agno.os.interfaces.agui import AGUI
from app.core.agno_agent import create_main_agent
from app.core.agno_medical_agents import (
    create_nurse_agent,
    create_doctor_agent,
    create_followup_generate_agent,
)


# 创建所有 Agent（复用工厂函数）
main_agent = create_main_agent()
nurse_agent = create_nurse_agent()
doctor_agent = create_doctor_agent()
followup_agent = create_followup_generate_agent()

# 创建 AgentOS 实例，注册所有 Agent
agent_os = AgentOS(
    id="AI-Care AgentOS",
    agents=[main_agent, nurse_agent, doctor_agent, followup_agent],
    interfaces=[
        AGUI(agent=main_agent),
        AGUI(agent=nurse_agent),
        AGUI(agent=doctor_agent),
        AGUI(agent=followup_agent),
    ],
)
app = agent_os.get_app()

print("\n" + "=" * 60)
print("  Agno AgentOS UI 启动中...")
print("  本地 API: http://localhost:7777")
print("  Web UI:   https://os.agno.com")
print("  (在 Web UI 中添加本地端口: http://localhost:7777)")
print("=" * 60)
print("\n  已注册 Agent:")
print("    - 小安 - 主对话 Agent (main_agent)")
print("    - 小护 - 护士 AI (nurse_agent)")
print("    - 智医 - 医生 AI (doctor_agent)")
print("    - 小安-随访生成 - 随访脚本生成 (followup_agent)")
print("=" * 60 + "\n")

if __name__ == "__main__":
    agent_os.serve(app="agno_ui:app", port=7777, reload=True)
