"""CareerPilot MCP Server implementation.

Exposes job search, analysis, resume generation, and interview prep as MCP tools.
Compatible with Claude Code, Cursor, Windsurf, and OpenClaw.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

from crawlers.aggregator import collect_all_jobs
from agents.analyst import analyze_jd, score_job, profile_company
from agents.tailor import generate_tailored_resume, generate_greeting
from agents.coach import extract_skill_tree, generate_study_path, generate_eight_part_essay, generate_mock_questions


def create_server() -> "Server":
    if not HAS_MCP:
        raise ImportError("MCP SDK not installed. Run: pip install mcp")

    server = Server("CareerPilot")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="CareerPilot_search",
                description="搜索AI/Agent/大模型相关的实习和工作岗位",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "description": "搜索关键词", "default": "AI Agent"},
                        "location": {"type": "string", "description": "目标城市", "default": "上海"},
                    },
                },
            ),
            Tool(
                name="CareerPilot_analyze",
                description="分析岗位JD并进行10维评分",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "jd_text": {"type": "string", "description": "岗位JD文本"},
                    },
                    "required": ["jd_text"],
                },
            ),
            Tool(
                name="CareerPilot_company",
                description="生成公司画像（薪资/评价/加班/评分）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "company_name": {"type": "string", "description": "公司名称"},
                    },
                    "required": ["company_name"],
                },
            ),
            Tool(
                name="CareerPilot_resume",
                description="根据JD生成定制简历",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "jd_info": {"type": "object", "description": "JD分析结果(来自CareerPilot_analyze)"},
                    },
                    "required": ["jd_info"],
                },
            ),
            Tool(
                name="CareerPilot_interview",
                description="生成面试准备资料包（技能树+学习路径+八股文+模拟面试）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "jd_info": {"type": "object", "description": "JD分析结果"},
                        "focus": {
                            "type": "string",
                            "enum": ["all", "skill_tree", "study_path", "eight_part", "mock"],
                            "default": "all",
                        },
                    },
                    "required": ["jd_info"],
                },
            ),
            Tool(
                name="CareerPilot_greeting",
                description="生成Boss直聘打招呼语",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "jd_info": {"type": "object", "description": "JD分析结果"},
                        "resume_data": {"type": "object", "description": "简历数据"},
                    },
                    "required": ["jd_info"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name == "CareerPilot_search":
            jobs = collect_all_jobs(
                arguments.get("keyword", "AI Agent"),
                arguments.get("location", "上海"),
                expand_keywords=True,
                enrich_details=True,
                detail_limit=20,
                use_browser_crawlers=False,
                allow_browser_login=False,
            )
            return [TextContent(type="text", text=json.dumps(jobs, ensure_ascii=False, indent=2))]

        elif name == "CareerPilot_analyze":
            jd_info = analyze_jd(arguments["jd_text"])
            total, details = score_job(jd_info)
            result = {"jd_info": jd_info, "score": total, "details": details}
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "CareerPilot_company":
            profile = profile_company(arguments["company_name"])
            return [TextContent(type="text", text=json.dumps(profile, ensure_ascii=False, indent=2))]

        elif name == "CareerPilot_resume":
            resume = generate_tailored_resume(arguments["jd_info"])
            return [TextContent(type="text", text=json.dumps(resume, ensure_ascii=False, indent=2))]

        elif name == "CareerPilot_interview":
            jd_info = arguments["jd_info"]
            focus = arguments.get("focus", "all")
            if focus == "skill_tree":
                result = extract_skill_tree(jd_info)
            elif focus == "study_path":
                tree = extract_skill_tree(jd_info)
                result = {"study_path": generate_study_path(tree)}
            elif focus == "eight_part":
                tree = extract_skill_tree(jd_info)
                result = {"eight_part_essay": generate_eight_part_essay(tree)}
            elif focus == "mock":
                result = {"mock_questions": generate_mock_questions(jd_info)}
            else:
                tree = extract_skill_tree(jd_info)
                result = {
                    "skill_tree": tree,
                    "study_path": generate_study_path(tree),
                    "eight_part_essay": generate_eight_part_essay(tree),
                    "mock_questions": generate_mock_questions(jd_info),
                }
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "CareerPilot_greeting":
            greeting = generate_greeting(arguments["jd_info"], arguments.get("resume_data", {}))
            return [TextContent(type="text", text=greeting)]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


if __name__ == "__main__":
    import asyncio
    if HAS_MCP:
        from mcp.server.stdio import stdio_server
        server = create_server()
        asyncio.run(stdio_server(server))
    else:
        print("MCP SDK not installed. Run: pip install mcp")
        print("Server would expose these tools: CareerPilot_search, CareerPilot_analyze, CareerPilot_company, CareerPilot_resume, CareerPilot_interview, CareerPilot_greeting")

