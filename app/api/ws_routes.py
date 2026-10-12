# [路由] 智能体任务下发 / 文件上传下载 / WebSocket 实时推送
# -----------------------------------------------------------------------------
# 来源：合并前 deep_agent_demo/api/server.py
# 改造点：
#   1. 原本它是一个独立的 FastAPI 应用（自带 app = FastAPI(...)），
#      这里改造成 APIRouter，由根目录 main.py 统一注册；
#   2. 原本的 @app.on_event("startup") 绑定事件循环的逻辑，
#      移到 main.py 的 lifespan 里（避免和 data-agent 原 lifespan 冲突）；
#   3. 所有 `agent./api./tools./utils.` 导入已改写为 `app.*`。
import asyncio
import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Form, UploadFile, WebSocket, WebSocketDisconnect, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.agent.main_agent import run_deep_agent
from app.api.monitor import manager

# 项目根目录：本文件位于 app/api/ 下，向上两级就是项目根
project_root = Path(__file__).resolve().parents[2]

# 产物目录 / 上传目录（不存在就自动建，保证首次启动不报错）
output_dir = project_root / "output"
output_dir.mkdir(exist_ok=True)
upload_dir = project_root / "upload"
upload_dir.mkdir(exist_ok=True)

# 本模块对外暴露的路由对象，main.py 会 include 它
ws_router = APIRouter(tags=["agent"])


class TaskRequest(BaseModel):
    """任务下发请求体：query 是用户的自然语言问题，thread_id 可选（不传则自动生成）"""
    query: str
    thread_id: str = None


@ws_router.post("/api/task")
async def run_task(request: TaskRequest):
    """
    智能体任务启动接口。

    目标：
    1. 接收用户自然语言指令；
    2. 在后台异步启动 Agent（create_task），不阻塞 HTTP 线程；
    3. 立即返回 thread_id，前端拿它去订阅 WebSocket 实时进度。
    """
    # 1. [ID 初始化] 没传就用 uuid 生成一个会话号
    thread_id = request.thread_id or str(uuid.uuid4())

    # 2. [后台执行] 把协程丢进当前事件循环，立刻返回
    asyncio.create_task(run_deep_agent(request.query, thread_id))

    # 3. [立即响应]
    return {"status": "started", "thread_id": thread_id}


@ws_router.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...), thread_id: str = Form(...)):
    """
    文件上传接口：把用户上传的文件存到 upload/session_{thread_id}/ 下，
    供 Agent 在后续任务里读取分析。
    """
    # 1. [目录准备] 每个会话一个独立目录，防止串台
    target_dir = upload_dir / f"session_{thread_id}"
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    # 2. [保存] 用二进制流写入，支持任意格式（图片/PDF/文本…）
    #    copyfileobj 是流式复制，不会把大文件一次性读进内存
    for file in files:
        file_path = target_dir / file.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file.filename)

    # 3. [响应] 返回成功保存的文件名列表
    return {"status": "uploaded", "files": saved_files}


@ws_router.get("/api/download")
async def download_file(path: str):
    """文件下载接口：按绝对路径下载，但做了越权校验（只允许 output 目录下的文件）。"""
    # 1. [安全检查] 解析绝对路径，并确认它在 output 目录内
    try:
        abs_path = Path(path).resolve()
        output_abs = output_dir.resolve()
        if not abs_path.is_relative_to(output_abs):
            return {"error": "拒绝访问: 只能下载输出目录下的文件"}
    except Exception:
        return {"error": "无效的路径参数"}

    # 2. [存在性检查]
    if not abs_path.exists():
        return {"error": "文件不存在"}

    # 3. [响应] 返回文件流，浏览器自动触发下载
    return FileResponse(abs_path, filename=abs_path.name)


@ws_router.get("/api/files")
async def list_files(path: str):
    """文件列表接口：列出某个会话产物目录下的所有文件（含大小/时间），前端据此渲染文件树。"""
    print(f"[DEBUG] 请求文件列表: {path}")

    # 1. [解析] + 越权校验：只允许访问 output 目录
    try:
        abs_path = Path(path).resolve()
        output_abs = output_dir.resolve()
        if not abs_path.is_relative_to(output_abs):
            print(f"[ERROR] 拒绝访问: {abs_path} 不在 {output_abs} 目录下")
            return {"error": "拒绝访问: 只能访问输出目录下的文件"}
    except Exception as e:
        print(f"[ERROR] 路径解析失败: {e}")
        return {"error": f"路径无效: {e}"}

    # 2. [存在性检查]
    if not abs_path.exists():
        return {"error": "目录不存在"}

    # 3. [遍历] 递归收集文件元数据
    files = []
    try:
        for file_path in abs_path.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "type": "file",
                    "path": str(file_path),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
    except Exception as e:
        print(f"[ERROR] 遍历文件失败: {e}")
        return {"error": str(e)}

    # 4. [排序] 按修改时间倒序，最新的排前面
    files.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    print(f"[DEBUG] 找到 {len(files)} 个文件")
    return {"files": files}


@ws_router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """
    WebSocket 实时通讯接口。

    职责：
    1. 建立长连接，按 thread_id 做会话级隔离；
    2. 进入消息监听循环，处理前端心跳（收到什么就回一个 pong）；
    3. 断连时清理连接记录。
    """
    # 1. [注册] 把连接登记到管理器，绑定 thread_id
    await manager.connect(websocket, thread_id)

    try:
        # 2. [循环] 保持连接活跃
        while True:
            data = await websocket.receive_text()
            # 3. [响应] 回一个 pong，前端据此判断连接是否存活
            await websocket.send_json({
                "type": "pong",
                "message": f"服务端已收到: {data}",
            })
    except WebSocketDisconnect:
        # 4. [清理] 客户端主动断开
        manager.disconnect(websocket, thread_id)
        print(f"[WebSocket] 客户端已断开: {thread_id}")
    except Exception as e:
        # 5. [异常] 出错也要断开，避免连接泄漏
        print(f"[WebSocket] 连接异常: {e}")
        manager.disconnect(websocket, thread_id)
