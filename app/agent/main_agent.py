# [核心] 智能体组装与执行逻辑
import shutil
from pathlib import Path

from deepagents import create_deep_agent

from app.agent.llm import model as llm
from app.agent.load_prompts import main_agent_config
from app.agent.sub_agents.rag_sub_agent import rag_sub_agent
from app.agent.sub_agents.db_sub_agent import db_sub_agent
from app.agent.sub_agents.network_search_agent import internet_sub_agent
from app.api.context import set_thread_context, set_session_context, reset_session_context
from app.api.monitor import monitor
from app.tools.markdown_tools import generate_markdown
from app.tools.pdf_tools import convert_md_to_pdf
from app.tools.upload_file_read_tool import read_file_content
from app.utils.logger_utils import logger

print(main_agent_config['system_prompt'])
main_agent = create_deep_agent(
    model=llm,
    system_prompt=main_agent_config['system_prompt'],
    subagents=[rag_sub_agent, db_sub_agent, internet_sub_agent],
    tools=[read_file_content, generate_markdown, convert_md_to_pdf]
)


def _report_agent_process(chunk):
    for key, value in chunk.items():
        # print(f"=={key}==")
        # print(value)
        if not value or "messages" not in value: continue
        message = value["messages"][-1]
        if key == "model":
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    # 区分子智能体和工具
                    if tool_call["name"] == "task":
                        # print( f"--准备调用子智能体{tool_call['args']['subagent_type']}, 参数：{tool_call['args']['description']}")
                        monitor.report_assistant(tool_call['args']['subagent_type'], tool_call['args']['description'])
                    else:
                        # print(f"--智能体准备调用工具{tool_call['name']}, 参数：{tool_call['args']}")
                        monitor.report_tool(tool_call['name'], tool_call['args'])
            elif message.content:
                # print(f"--智能体返回最终结果: {message.content}")
                monitor.report_task_result(message.content)
        # elif key == "tools":
        #     if message.name == "task":
        #         print(f"--调用子智能体返回的结果为：{message.content}")
        #     else:
        #         print(f"--调用工具{message.name}返回的结果为：{message.content}")


def _describe_error(e: Exception) -> str:
    """
    把底层异常翻译成【人能看懂 + 能直接照做】的中文原因。

    为什么需要它：
        LLM 调用失败抛出的原始异常长这样 ——
        "Error code: 401 - {'error': {'message': 'Invalid API-key provided...', 'code': 'invalid_api_key'}}"
        直接甩给用户等于没说。这里按「HTTP 状态码 / 关键字」归类，给出可执行的排查方向。

    返回:
        str: 一句话原因，例如 "API Key 无效或已过期（401），请检查 .env 里的 OPENAI_API_KEY"
    """
    raw = str(e).lower()

    # (关键字列表, 可读原因)。按「越具体越靠前」排列，命中即返回
    rules = [
        (["invalid_api_key", "invalid api-key", "unauthorized", "401", "authentication"],
         "API Key 无效或已过期（401），请检查 .env 里的 OPENAI_API_KEY"),
        (["model_not_permitted", "permission", "not supported", "403", "forbidden"],
         "无权访问该模型（403），请确认账号已开通该模型，或 MODEL_NAME 是否写对"),
        (["model_not_found", "does not exist", "no such model", "404"],
         "模型或接口地址不存在（404），请检查 .env 里的 MODEL_NAME 与 OPENAI_BASE_URL"),
        (["rate limit", "rate_limit", "quota", "insufficient", "arrear", "429", "overloaded"],
         "请求被限流或账户额度不足（429），请稍后重试或检查账户余额"),
        (["context length", "context_length", "maximum context", "too long", "token"],
         "上下文超出模型上限，请缩短输入或换用更大上下文的模型"),
        (["timeout", "timed out", "readtimeout", "connecttimeout"],
         "请求模型服务超时，请检查网络后重试"),
        (["connection", "max retries", "getaddrinfo", "ssl", "proxy", "unreachable"],
         "无法连接模型服务，请检查网络/代理与 OPENAI_BASE_URL 是否可达"),
    ]
    for keywords, hint in rules:
        if any(kw in raw for kw in keywords):
            return hint

    # 兜底：实在认不出来，至少把异常类型告诉用户
    return f"未识别的错误（{type(e).__name__}），请查看服务端日志"


async def run_deep_agent(query: str, thread_id: str):
    # 在调用agent之前，保存thread_id, session_dir_str
    # 保存thread_id
    thread_token = set_thread_context(thread_id)
    # 生成session_dir_str， 再保存session_dir_str，, 并向前端发送session_dir_str
    project_dir = Path(__file__).parents[2].resolve()  # 项目根目录
    session_dir = project_dir / "output" / f"session_{thread_id}"  # 拼接生成sesion目录path对象
    session_dir.mkdir(parents=True, exist_ok=True)  # 确保输出目录存在
    session_dir_str = str(session_dir).replace("\\", "/")  # 生成完整路径字符串
    session_token = set_session_context(session_dir_str)  # 保存session_dir_str
    monitor.report_session_dir(session_dir_str)  # 告诉前端，当前会话的输出目录, 浏览器才能在右侧显示会话文件列表

    # 将upload中的文件拷贝到session目录中
    upload_dir = project_dir / "upload" / f"session_{thread_id}"
    uploaded_info = ''  # 关于要优先读取上传的文件的提示词
    if upload_dir.exists():
        # 得到所有文件的列表
        file_names = [item.name for item in upload_dir.iterdir() if item.is_file()]
        for name in file_names:
            shutil.copy2(upload_dir / name, session_dir / name)
        uploaded_info = (f"\n    [已上传文件] 已加载到工作目录:\n" +
                         "\n".join([f"    - {f}" for f in file_names]) +
                         "\n    请优先使用工具读取并参考这些文件。")

    # 得到工作区目录的相对路径
    relative_session_dir_str = str(session_dir.relative_to(project_dir)).replace("\\", "/")
    path_instruction = f"""
            【工作环境指令】
            工作目录: {relative_session_dir_str}

            {uploaded_info}

            规则：
            1. 新生成文件必须保存到工作目录：'{relative_session_dir_str}'
            2. 读取已上传的文件时，请直接将文件名（例如：'开篇.txt'）作为 filename 参数传入（read_file_content）读取工具，不要带上任何目录前缀。
            3. 使用相对路径，禁止使用绝对路径
            4. 若存在上传文件，请先分析内容
            """

    try:
        # 执行agent,遍历过程数据，并将特定数据信息发送给前端
        result = main_agent.astream({
            "messages": [{
                "role": "user",
                "content": f"问题：{query}, 补充描述: {path_instruction}"
            }]
        })
        async for chunk in result:
            # 遍历每个chunk,向前端发送当前状态及数据
            _report_agent_process(chunk)
    except Exception as e:
        # ----------------------------------------------------------------
        # 失败处理：把真实原因透出去，别再只丢一句"执行最终失败了"
        # 之前这里只发固定文案，用户在前端看到的就是一句废话，
        # 完全不知道是 401 / 超时 / 额度 问题，只能来翻服务端日志。
        # ----------------------------------------------------------------
        hint = _describe_error(e)                      # 归类后的可读原因
        raw = " ".join(str(e).split())[:500]           # 压掉换行和多余空白，避免刷屏

        # 1) 完整文案：前端拿到即可直接展示，不用再猜
        message = f"智能体执行失败：{hint}"

        # 2) 服务端日志：保留全量报错 + 堆栈，方便深挖
        logger.error(f"{message}｜原始报错: {raw}", exc_info=True)

        # 3) 推送给前端：message 展示用，raw 供前端折叠查看
        monitor.report_error(message, hint=hint, raw=raw, error_type=type(e).__name__)
    finally:  # 最终都要重置保存的thread_id和session_dir
        reset_session_context(session_token, thread_token)

if __name__ == "__main__":
    # =====================================================================
    # 本地冒烟测试入口：python -m agent.main_agent "你的测试问题"
    # 不启动 FastAPI，直接在当前进程运行主智能体，进度输出到控制台
    # =====================================================================
    import asyncio
    import builtins
    import sys
    import time
    import uuid

    # 1) 挂载"假运行时"，让 monitor 的进度事件打印到控制台
    #    （monitor._emit 检测到 builtins.runtime.stream_writer 就会调用它，
    #      这正是 deepagents 脚本模式的机制，无需 WebSocket）
    class _ConsoleRuntime:
        def __init__(self):
            self.stream_writer = lambda payload: print(
                f"  [monitor] {payload['event']:>14} | {payload['message']}"
            )

    builtins.runtime = _ConsoleRuntime()

    # 2) 测试问题：优先取命令行参数，否则用内置示例
    query = (sys.argv[1] if len(sys.argv) > 1
             else "请使用数据库查询助手查询库存最少的10种药品，列出药品名称、库存数量和规格，生成一份库存预警清单Markdown文件")
    thread_id = f"local_test_{uuid.uuid4().hex[:8]}"  # 随机线程号，避免污染正式会话

    print("=" * 60)
    print(f"测试问题 : {query}")
    print(f"线程 ID  : {thread_id}")
    print("=" * 60)

    # 3) 执行主智能体（内部会创建 output/session_<thread_id> 目录）
    start = time.perf_counter()
    asyncio.run(run_deep_agent(query=query, thread_id=thread_id))
    elapsed = time.perf_counter() - start

    # 4) 结束提示
    print("=" * 60)
    print(f"执行结束，耗时 {elapsed:.1f}s")
    print(f"输出目录: output/session_{thread_id}")
    print("=" * 60)
# 基于网络搜索到的沃华医药信息，生成一份调研报告：先创建Markdown文件，再转换为PDF
# 综合使用网络搜索助手和数据库查询助手，分析沃华医药主力产品与市场表现，生成完整分析报告PDF