# [入口] 统一 FastAPI 应用 —— 合并后 data-agent 平台的唯一启动文件
# -----------------------------------------------------------------------------
# 合并前有两套入口：
#   · data-agent  的 main.py  -> 只有 NL2SQL 的 REST 路由
#   · deep_agent_demo 的 api/server.py -> 自带一个 FastAPI(任务下发 + WebSocket)
# 现在合成一个 app，同时挂两类路由：
#   1) query_router  : NL2SQL 查询（REST）
#   2) ws_router     : 智能体任务下发 / 文件上传下载 / WebSocket 实时推送
import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.monitor import manager
from app.api.routers.query_router import query_router
from app.api.ws_routes import ws_router
from app.core.context import request_id_ctx_var
from app.core.lifespan import lifespan as core_lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    组合生命周期。

    为什么不用 @app.on_event("startup")：
        那样会和 data-agent 原有的 lifespan（初始化 ES/Qdrant/MySQL 等客户端）冲突，
        FastAPI 不允许二者混用。这里用 async with 把原 lifespan 包起来，
        在它初始化完成之后，再把当前事件循环绑定给 WebSocket 管理器 ——
        deepagents 侧靠 run_coroutine_threadsafe 推送进度，必须拿到这个 loop。
    """
    async with core_lifespan(app):
        # 绑定事件循环给 WS 管理器（实时推送给前端的前提）
        manager.set_loop(asyncio.get_running_loop())
        print(f"[Server] WebSocket Manager bound to loop: {id(manager.loop)}")
        yield


# 创建FastAPI应用实例
app = FastAPI(lifespan=lifespan)

# ---------------------------------------------------------------------------
# CORS 中间件（必须）
#   前端(5173) 与 后端(8005) 不同源，浏览器发 POST 前会先发 OPTIONS 预检。
#   缺了它 → 预检返回 405 Method Not Allowed → 浏览器判定跨域失败
#   → 前端报 "请求失败：Network Error"。
#   （WebSocket 不受 CORS 限制，所以界面显示"已连接"、一发消息却失败，就是这个症状。）
#   开发环境放开全部来源；上线时把 allow_origins 收窄成真实域名。
#   注意：allow_origins=["*"] 时 allow_credentials 必须为 False。
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由：NL2SQL 查询 + Agent 任务/WebSocket
app.include_router(query_router)
app.include_router(ws_router)


# 整合中间件->设置异步协程上下文变量
@app.middleware("http")
async def add_request_cxt_var(request: Request, call_next):
    # 设置异步协程上下文变量
    request_id_ctx_var.set(uuid.uuid4())
    return await call_next(request)


if __name__ == "__main__":
    # 本地直接启动：python main.py
    # 注意：这里传 app 对象，而不是 "main:app" 字符串。
    #   传字符串会让 uvicorn 再把 main 模块 import 一遍，导致
    #   主智能体（deepagents 组装 + 打印 prompt）被重复构建两次。
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005, reload=False)
