# tools.py — 三个工具的定义 + 执行函数

import os
import requests
from duckduckgo_search import DDGS


def get_tool_definitions():
    """返回给 DeepSeek 的 tools 列表（OpenAI 格式）"""
    return [
        {
            "type": "function",
            "function": {
                "name": "duckduckgo_search",
                "description": "搜索互联网获取最新行业数据、研报、市场信息。每次搜索返回多个相关结果。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词，建议用中英文混合提高结果质量"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "返回结果数量，默认5"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "jina_fetch",
                "description": "抓取指定URL网页的完整正文内容，用于深度阅读某篇文章或报告。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "要抓取的网页URL"
                        }
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "notion_write",
                "description": "将调研报告内容写入用户的 Notion 页面，并保存为本地 report.md 文件。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "报告标题"
                        },
                        "content": {
                            "type": "string",
                            "description": "Markdown 格式的完整调研报告内容"
                        }
                    },
                    "required": ["title", "content"]
                }
            }
        }
    ]


def run_tool(tool_name: str, tool_input: dict) -> str:
    """执行工具并返回结果字符串"""
    if tool_name == "duckduckgo_search":
        return _ddg_search(tool_input["query"], tool_input.get("max_results", 5))
    elif tool_name == "jina_fetch":
        return _jina_fetch(tool_input["url"])
    elif tool_name == "notion_write":
        return _notion_write(tool_input["title"], tool_input["content"])
    else:
        return f"未知工具: {tool_name}"


def _ddg_search(query: str, max_results: int = 5) -> str:
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
        if not raw:
            return "未找到相关结果"
        results = []
        for i, r in enumerate(raw, 1):
            results.append(
                f"{i}. **{r.get('title', '')}**\n"
                f"   URL: {r.get('href', '')}\n"
                f"   摘要: {r.get('body', '')[:300]}...\n"
            )
        return "\n".join(results)
    except Exception as e:
        return f"搜索失败: {str(e)}"


def _jina_fetch(url: str) -> str:
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"Accept": "text/plain", "X-Return-Format": "markdown"}

    try:
        resp = requests.get(jina_url, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.text[:5000]
    except Exception as e:
        return f"抓取失败: {str(e)}"


def _notion_write(title: str, content: str) -> str:
    """写入 Notion + 保存本地 report.md"""

    # 1. 保存本地文件
    with open("report.md", "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n{content}")

    # 2. 写入 Notion
    page_id = os.environ.get("NOTION_PAGE_ID", "")
    notion_key = os.environ.get("NOTION_API_KEY", "")

    if not page_id or not notion_key:
        return "⚠️ 未配置 NOTION_API_KEY 或 NOTION_PAGE_ID，已保存为 report.md"

    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    blocks = []
    for line in content.split("\n"):
        if not line.strip():
            continue
        if line.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                            "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
        elif line.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                            "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:]}}]}})
        elif line.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                            "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:]}}]}})
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
        else:
            blocks.append({"object": "block", "type": "paragraph",
                            "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}})

    divider_blocks = [
        {"object": "block", "type": "divider", "divider": {}},
        {"object": "block", "type": "heading_2",
         "heading_2": {"rich_text": [{"type": "text", "text": {"content": f"📊 {title}"}}]}}
    ] + blocks[:95]

    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    resp = requests.patch(url, headers=headers, json={"children": divider_blocks})

    if resp.status_code == 200:
        return f"✅ 成功写入 Notion 页面，共 {len(divider_blocks)} 个块"
    else:
        return f"❌ Notion 写入失败: {resp.status_code} - {resp.text[:200]}"
