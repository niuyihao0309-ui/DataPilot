# data-agent —— 企业数据智能体平台（方案 A 落地版）

> 落地路径：`D:/ke_cheng/people_data/data-agent`
> 合并来源：`xiangm-NL2SQL/data-agent` + `deep_agent_demo` + `xiangm-DeepAgent`
> 定位：**企业经营分析助手** —— 用户一句自然语言提问，系统自动完成
> 「查真实数据（NL2SQL）+ 查内部资料（知识库/文档/联网）+ 汇总出报告」。

---

## 一、这个项目是干什么的

| 用户输入 | 系统做什么 | 产出 |
|---|---|---|
| "上季度华东区药品卖得怎么样？顺便看看说明书禁忌，出个报告" | ① NL2SQL 查真实业务库 ② 查知识库/文档/联网补充 ③ 汇总 | 一份带数据+佐证+建议的经营分析报告 |

**重点在"分析"，不是"查询"。** 面向不会写 SQL 的业务/老板。

---

## 二、目录结构

```
data-agent/
├── app/
│   ├── agent/                    # Agent 编排层
│   │   ├── graph.py state.py     #   [data-agent] LangGraph NL2SQL 主图(13 节点)
│   │   ├── nodes/                #   [data-agent] recall / filter / generate / validate ...
│   │   ├── llm.py                #   [合并] 统一 LLM(配置驱动) + model 别名
│   │   ├── load_prompts.py       #   [demo] 读 prompts.yml
│   │   ├── main_agent.py         #   [demo] deepagents 主智能体 + 执行/错误归类
│   │   └── sub_agents/           #   [demo] rag / db / internet 三个子智能体
│   ├── api/                      # Web 层
│   │   ├── routers/ schemas/ dependencies.py   # [data-agent] NL2SQL REST
│   │   ├── ws_routes.py          #   [demo 改造] 任务下发/上传下载/WebSocket
│   │   ├── context.py            #   [demo] ContextVar 会话隔离
│   │   └── monitor.py            #   [demo] 进度上报(WS + 脚本双通道)
│   ├── clients/                  # [data-agent] ES / Qdrant / MySQL / embedding 客户端管理
│   ├── models/                   # [data-agent] es / mysql / qdrant 三套模型(分桶)
│   ├── repositories/             # [data-agent] es / mysql / qdrant 三套仓储(分桶)
│   ├── services/ conf/ core/ scripts/   # [data-agent] 服务 / 配置 / 生命周期 / 脚本
│   ├── prompt/                   # [合并] prompt_loader.py(.prompt) + prompts.yml
│   ├── tools/                    # [demo] mysql / ragflow / 联网 / pdf / markdown / 文件读取
│   └── utils/                    # [demo] logger / path / converter
├── conf/                         # [data-agent] app_config.yaml / meta_config.yaml / text_config.yaml
├── prompts/                      # [data-agent] 8 个 .prompt 模板
├── docker/                       # [data-agent + redis] ES/Kibana/MySQL/Qdrant/Embedding/Redis
├── skills/                       # [DeepAgent] code-reviewer / emoji-translator / ai-travel-planner
├── ui/                           # [demo] Vue3 前端(已剔除 node_modules)
│   ├── Dockerfile  nginx.conf    #   [新增] 前端镜像：node 构建 → nginx 托管
├── main.py                       # [合并] 统一入口：REST + WebSocket 一个 app
├── app_switch.bat                # [新增] 项目开关：Docker 在跑就起全栈，不在就跳过
├── .dockerignore                 # [新增] 镜像构建排除清单
├── pyproject.toml                # [合并] 三方依赖并集
├── .env / .env.example           # 环境变量(.env 含真实密钥，已在 .gitignore)
└── README.md
```

---

## 三、合并时改了什么（重点）

| # | 改动 | 原因 |
|---|---|---|
| 1 | demo 侧导入前缀统一改写 `agent./api./tools./utils.` → `app.*` | 两套包名冲突，统一到 `app` 命名空间 |
| 2 | `app/agent/llm.py` 增加 `model = llm` 别名 | demo 老代码用 `from agent.llm import model`，加别名免改一堆 |
| 3 | `app/agent/main_agent.py` 项目根 `parents[1]` → `parents[2]` | 多了一层 `app/`，否则 output/upload 会建错位置 |
| 4 | demo 的 `api/server.py` 改造成 `app/api/ws_routes.py`（APIRouter） | 原来它是独立 FastAPI app，现在并入统一 app |
| 5 | `main.py` 用 `async with core_lifespan(app)` 组合生命周期 | 绑定 WS 事件循环，且不与原 lifespan 冲突 |
| 6 | `docker-compose.yaml` 新增 `redis` 服务 + `redis_data` 卷 | deepagents 侧 LangGraph checkpoint 需要 |
| 7 | `pyproject.toml` 三方依赖取并集（deepagents 取 0.7.6） | 统一依赖，一次 `uv sync` 搞定 |
| 8 | 剔除 `npm>=0.1.1`（原是误加的非相关包） | 澄清依赖 |

### 3.1 首次启动实测又修掉的坑（2026-10-11）

| # | 问题 | 表现 | 修法 |
|---|---|---|---|
| 9 | `sqlalchemy` 没带 `[asyncio]` extra | 容器里 `No module named 'greenlet'`，backend 反复重启 | `pyproject.toml` 改 `sqlalchemy[asyncio]`，重新 `uv lock` + 重建 |
| 10 | compose 项目名默认取目录名 `docker` | 与 `xiangm-NL2SQL/docker` **撞名** → 共用 MySQL 8.4 旧卷，报 `Cannot downgrade from 80411 to 80046` | compose 顶层加 `name: people-data`，走独立新卷 |
| 11 | `app/utils/converter_utils.py` 顶层 `import win32com` | Linux 容器 `No module named 'win32com'`，backend 起不来 | 改成**函数内延迟导入**，非 Windows 返回友好提示 |
| 12 | `meta_knowledge_service.py` 写 meta 库的代码被整段注释 | meta 库全空 → NL2SQL「合并召回信息」报 `'NoneType' object has no attribute 'name'` | 恢复写入 + 显式 `session.commit()` |
| 13 | `expire_on_commit=True` | commit 后读 ORM 属性触发惰性加载 IO → `MissingGreenlet` | 改 `expire_on_commit=False` |
| 14 | 构建脚本不幂等 | 重跑报 `Duplicate entry 'xxx' for key 'column_info.PRIMARY'` | 构建前 TRUNCATE meta 四表 + 删 Qdrant 两集合 |
| 15 | `main.py` 缺 `CORSMiddleware` | 前端一发消息就报 `请求失败：Network Error`（OPTIONS 预检 405） | 补上 CORS 中间件（原 demo 的 `api/server.py` 本来有，改造成 APIRouter 时丢了） |

---

## 四、启动步骤（本机直跑）

> 前提：已装 Docker Desktop（WSL2 后端）、uv。
> 想「一键 Docker 起全栈」请看 **第五节**；本节讲的是本机直接跑后端 / 前端的开发方式。

```bash
# 1) 装依赖（生成合并后的锁文件）
cd D:/ke_cheng/people_data/data-agent
uv sync

# 2) 准备 embedding 模型（1.3G，未随项目复制）
#    方式一：把原模型拷过来
#      cp -r D:/ke_cheng/xiangm-NL2SQL/data-agent/docker/embedding/bge-large-zh-v1.5 \
#            D:/ke_cheng/people_data/data-agent/docker/embedding/
#    方式二：从 HuggingFace 重新下载 BAAI/bge-large-zh-v1.5 到该目录

# 3) 起基础设施（ES/Kibana/MySQL/Qdrant/Embedding/Redis）
cd docker
docker compose up -d

# 4) 起后端
cd ..
uv run python main.py        # http://localhost:8005
```

> 注意：`.env` 已从 demo 拷贝（含真实密钥，已 gitignore）。换机器时参考 `.env.example`。

### 4.1 主入口（唯一）

项目只有一个对外入口：**根目录 `main.py`**，它是一个 FastAPI 应用，端口 **8005**。
启动方式：

```bash
uv run python main.py                 # 直接跑（等价 uvicorn main:app --port 8005）
```

对外接口（一个 app 全包了）：

| 方法 | 路径 | 作用 | 来源 |
|---|---|---|---|
| POST | `/api/query` | NL2SQL 查询 | 原 data-agent |
| POST | `/api/task` | 下发智能体任务，返回 thread_id | 原 demo |
| POST | `/api/upload` | 上传文件到会话目录 | 原 demo |
| GET | `/api/download` | 下载产物文件 | 原 demo |
| GET | `/api/files` | 列出会话产物目录 | 原 demo |
| WS | `/ws/{thread_id}` | 实时推送执行进度 | 原 demo |

### 4.2 调试入口（不起服务，直接跑，从简到繁）

```bash
uv run python -m app.agent.llm                       # ① 最轻：只测 .env 里 LLM 能不能通
uv run python -m app.agent.main_agent "查询库存最少的10种药品"   # ② 跑主智能体(控制台看进度)
uv run python -m app.agent.graph                      # ③ 跑 NL2SQL 图(需 ES/Qdrant/MySQL 已起)
uv run python -m app.scripts.build_meta_knowledge     # ④ 构建元数据知识库(灌 ES + Qdrant)
```

### 4.3 前端

```bash
cd ui
npm install
npm run dev        # http://localhost:5173
```

### 4.4 ⚠️ MySQL 端口有两套说法（启动前先统一）

| 来源 | 端口 | 库 | 用户 |
|---|---|---|---|
| `docker-compose.yaml` | 3306 | meta / dw | itwwy |
| `conf/app_config.yaml` | 3306 | meta / dw | itwwy |
| **`.env`** | **3307** | pharma_db | root |

`.env` 的 `MYSQL_PORT=3307` 是 demo 时代的独立容器遗留，与当前编排（3306）不一致 ——
demo 侧的 `app/tools/mysql_tools.py` 会连不上。**这是"统一 MySQL 访问"待办要解决的事**，临时可先把 `.env` 的端口改成 3306 验证。


---

## 五、一键开关（Docker 起全栈）

前后端也已 Docker 化，一条命令即可起全栈。

### 5.1 用开关（推荐）

双击项目根目录的 **`app_switch.bat`**：

| 运行方式 | 行为 |
|---|---|
| 直接双击 / `start` | **Docker 没开就自动启动 Docker Desktop 并轮询等待就绪** → 起全栈（基础设施+后端+前端）→ **5 秒后自动打开前端页面**（真·一下全搞定） |
| `app_switch.bat stop` | 停止全部容器 |
| `app_switch.bat status` | 查看容器状态 |
| `app_switch.bat logs` | 跟踪后端日志 |
| `app_switch.bat build` | 强制重建前后端镜像后再启动（**改了代码后用这个**） |

启动后：

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:5173 |
| 后端 | http://localhost:8005 |
| 接口文档 | http://localhost:8005/docs |
| Kibana | http://localhost:5601 |

### 5.2 想开机自动拉起？

把 `app_switch.bat` 的**快捷方式**丢进 Windows 启动目录：

```
Win + R  →  输入 shell:startup  →  回车  →  把快捷方式粘进去
```

这样每次登录时会自动：**Docker 没开就拉起 Docker Desktop（等它就绪）→ 起全栈 → 打开前端页面**。

> 注：这是「按需拉起」，**不修改 Docker Desktop 自身的开机自启设置**（那个仍保持关闭）。

### 5.3 手动命令（等价）

```bash
cd docker
docker compose up -d              # 起全部（含前端 + 后端）
docker compose up -d --build      # 改了代码，先重建镜像
docker compose logs -f backend    # 看后端日志
docker compose down               # 停
```

### 5.4 容器怎么连到基础设施（关键设计）

后端容器里的 `localhost` 指的是容器自己，连不到宿主机的 MySQL / ES / Qdrant。解决办法：

- compose 给 backend 传 `DATA_AGENT_HOST=host.docker.internal`；
- `app/conf/app_config.py` 检测到这个变量后，**把所有服务的 host 一次性替换掉**（不设置则保持原样，本机直跑不受影响）；
- demo 侧的工具直接读 `MYSQL_HOST`，compose 里同样改成了 `host.docker.internal`。

> 结果：同一份 `conf/app_config.yaml`，本机直跑和容器里跑都能用，**不用维护两份配置**。

### 5.5 首次构建慢/失败？换国内源

镜像构建时若卡在下载依赖，用 build-arg 换镜像源：

```bash
cd docker
docker compose build \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  backend frontend
docker compose up -d
```

---

## 六、待办（下一步要做的事）

| 优先级 | 待办 | 说明 |
|---|---|---|
| ✅ 已完成 | 前后端 Docker 化 + 一键开关 | 见第五节 |
| ✅ 已完成 | 跑通全栈 + 知识库构建 + 端到端 NL2SQL | 2026-10-11 实测：11 阶段流水线跑通，返回真实销售额 |
| P0 | 统一 MySQL 访问 | demo 的 `mysql_tools.py`(同步 mysql-connector) 与 data-agent 的 async repository 并存，后续应统一 |
| P1 | 把 NL2SQL 接成主 Agent 的一个子智能体 | 目前 NL2SQL(graph) 与主 Agent(main_agent) 还是两条平行入口 |
| P1 | 补 LangGraph Redis checkpoint | 依赖已加，代码里还没接 |
| P2 | 统一 prompt 加载器 | 现在 `.prompt`(data-agent) 和 `prompts.yml`(demo) 两套并存 |
| P2 | 前端 `ui/` 接上统一后端接口 | ui 来自 demo，指向的接口需与新入口对齐 |

---

## 七、注意事项

- **LLM 配置只认 `.env`**（当前=硅基流动 SiliconFlow）。`conf/app_config.yaml` 里的 `llm:` 段已废弃、不再生效，要换模型改 `.env` 的 3 行即可。
- **`.env` 含真实密钥**，已加入 `.gitignore`，切勿提交。
- `app/agent/main_agent.py` 在 import 时会构建主智能体并 `print` 系统提示词，属原 demo 行为。
- `app/utils/converter_utils.py` 依赖 Windows 的 Word COM（pywin32）。已改为**函数内延迟导入**：非 Windows（容器）里模块可正常加载，只有真正调用"MD→PDF"时才返回"仅 Windows 可用"提示，不会拖垮 backend。
- **知识库构建**（改了 `conf/meta_config.yaml` 后重跑）：
  ```bash
  docker exec data-agent-backend python -m app.scripts.build_meta_knowledge -c ./conf/meta_config.yaml
  ```
  脚本已做幂等处理（先清 meta 四表 + Qdrant 两集合），可反复执行。
- **embedding 模型已就位**（`docker/embedding/bge-large-zh-v1.5`，1.3G，从 xiangm-NL2SQL 拷入）。
- ⚠️ **`app_switch.bat` 必须存成 GBK（ANSI）编码**：中文 Windows 的 cmd 按 936 代码页解析批处理，若存成 UTF-8，中文会把命令行**拆断**，报满屏 `'xxx' 不是内部或外部命令`。脚本内已配 `chcp 936`，以后改这个文件注意别用 UTF-8 保存。
