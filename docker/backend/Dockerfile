# =============================================================================
# 后端镜像：data-agent（FastAPI + LangGraph + deepagents）
# 构建上下文 = 项目根目录（在 docker-compose.yaml 里配的 context: ..）
# =============================================================================
FROM python:3.12-slim

# PyPI 源。国内构建慢/失败时可改成清华镜像：
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple backend
ARG PIP_INDEX_URL=https://pypi.org/simple

# 装 uv：用 pip 装，而不是 COPY --from=ghcr.io/astral-sh/uv。
# 这样少依赖一个外部镜像仓库（ghcr.io 在部分网络下也不可达），只需 PyPI 通即可。
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} uv

# env 说明：
#   UV_PROJECT_ENVIRONMENT  把虚拟环境直接建在系统 Python 下（省一层目录，uv run 能直接找到）
#   UV_LINK_MODE=copy       避免 overlayfs 上硬链接告警
#   UV_COMPILE_BYTECODE=1   预编译 .pyc，容器启动更快
#   PYTHONUNBUFFERED=1      日志实时输出，不被缓冲
#   TZ                      时区设成东八区，日志时间对得上
ENV UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    PYTHONPATH=/app \
    UV_DEFAULT_INDEX=${PIP_INDEX_URL}

WORKDIR /app

# 先只拷依赖清单：依赖没变就命中缓存，不用每次重装
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

# 再拷业务代码（.dockerignore 已排除 .env / 前端 / 大模型权重等）
COPY . .

# 说明：运行时目录 output / upload 由 docker-compose 用卷挂到宿主机
EXPOSE 8005

# 注意：这里必须用 python main.py（而不是 uvicorn 命令行），
# 因为 main.py 内部传的是 app 对象，能避免主智能体被重复构建。
CMD ["uv", "run", "python", "main.py"]
