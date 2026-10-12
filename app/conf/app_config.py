from dataclasses import dataclass
import os
from pathlib import Path

from omegaconf import OmegaConf


# 日志配置
@dataclass
class File:
    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class Console:
    enable: bool
    level: str


@dataclass
class LoggingConfig:
    file: File
    console: Console


# 数据库配置
@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass
class QdrantConfig:
    host: str
    port: int
    embedding_size: int


@dataclass
class EmbeddingConfig:
    host: str
    port: int
    model: str


@dataclass
class ESConfig:
    host: str
    port: int
    index_name: str


@dataclass
class LLMConfig:
    model_name: str
    api_key: str
    base_url: str


@dataclass
class AppConfig:
    logging: LoggingConfig
    db_meta: DBConfig
    db_dw: DBConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig

# Path(__file__).parents[1] / 'conf' / 'app_config.yaml'
config_file = Path(__file__).parents[2] / 'conf' / 'app_config.yaml'
context = OmegaConf.load(config_file)
schema = OmegaConf.structured(AppConfig)
app_config: AppConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))


# ---------------------------------------------------------------------------
# 容器内运行支持（本机直跑不受影响）
# ---------------------------------------------------------------------------
# 问题：这份配置里各服务的 host 都写的 localhost，本机直跑时没问题；
#     但装进 Docker 后，localhost 指的是容器自己，连不到宿主机上映射出来的端口。
#
# 解决：提供一个统一开关环境变量 DATA_AGENT_HOST。
#     · 不设置  -> 保持配置原样（本机直跑，无人察觉）
#     · 设置了  -> 把所有服务的 host 一次性替换掉
#     容器里由 docker-compose 传 DATA_AGENT_HOST=host.docker.internal。
#
# 为什么一个变量就够：所有基础设施（MySQL/ES/Qdrant/Embedding）都在同一台宿主机上，
#     且都把端口映射到了宿主机，所以它们对外的「主机名」是同一个。
_host_override = os.environ.get("DATA_AGENT_HOST")
if _host_override:
    for _section in ("db_meta", "db_dw", "qdrant", "es", "embedding"):
        setattr(getattr(app_config, _section), "host", _host_override)