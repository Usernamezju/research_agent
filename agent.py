# agent.py — Agent 核心逻辑，使用 DeepSeek（OpenAI 兼容接口）

import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from tools import get_tool_definitions, run_tool

load_dotenv()

SYSTEM_PROMPT = """你是一个专业的行业前期调研助手。当用户给出调研主题时，你必须：

1. 调用 duckduckgo_search 搜索该主题的最新行业报告（至少搜索3次，使用不同关键词）
   - 第1次：中文搜索 "主题 市场规模 2025"
   - 第2次：英文搜索 "topic market report 2025"
   - 第3次：搜索 "主题 竞争格局 主要企业"

2. 对搜索结果中最有价值的2-3个URL调用 jina_fetch 获取全文

3. 整合所有信息，生成结构化调研大纲，必须包含：
   ## 一、行业现状
   ## 二、市场规模与增长趋势（含具体数据）
   ## 三、核心痛点与用户需求
   ## 四、竞争格局与主要玩家
   ## 五、技术瓶颈分析
   ## 六、市场机会与建议
   ## 七、参考资料（含URL来源）

4. 调用 notion_write 将完整报告写入 Notion

每个数据点必须标注来源URL，不能出现无来源的论断。"""


def run_research_agent(topic: str, callback=None):
    """
    运行调研 Agent（DeepSeek 版本）。
    callback(event_type, data) 用于向 UI 推送事件。
    """

    def emit(event_type, data):
        if callback:
            callback(event_type, data)

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请帮我调研：{topic}"}
    ]
    tools = get_tool_definitions()

    emit("thinking", f"开始调研主题：{topic}")

    while True:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

        choice = response.choices[0]
        msg = choice.message

        # 推送思考文字
        if msg.content:
            emit("thinking", msg.content)

        # 把 assistant 消息加入历史
        messages.append(msg.model_dump(exclude_unset=False))

        # 结束
        if choice.finish_reason == "stop":
            emit("done", msg.content or "调研完成")
            break

        # 工具调用
        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            tool_results = []

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except Exception:
                    tool_input = {}

                emit("tool_call", {"name": tool_name, "input": tool_input})

                try:
                    result = run_tool(tool_name, tool_input)
                    success = not result.startswith("❌")
                    emit("tool_result", {"name": tool_name, "result": result, "success": success})
                except Exception as e:
                    result = f"执行出错: {str(e)}"
                    emit("tool_result", {"name": tool_name, "result": result, "success": False})
                    emit("error", result)

                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result
                })

            messages.extend(tool_results)

        else:
            emit("error", f"意外停止原因: {choice.finish_reason}")
            break


# ─── CLI 入口 ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    def cli_callback(event_type, data):
        if event_type == "thinking":
            print(f"[思考] {str(data)[:200]}")
        elif event_type == "tool_call":
            print(f"\n>>> [工具调用] {data['name']}")
            for k, v in data["input"].items():
                print(f"    {k}: {str(v)[:100]}")
        elif event_type == "tool_result":
            icon = "OK" if data["success"] else "FAIL"
            print(f"<<< [{icon}] {data['name']} | {str(data['result'])[:150]}\n")
        elif event_type == "done":
            print("\n===== 最终报告 =====")
            print(data)
        elif event_type == "error":
            print(f"[错误] {data}")

    topic = sys.argv[1] if len(sys.argv) > 1 else "高校AI烹饪设备市场"
    run_research_agent(topic, callback=cli_callback)
