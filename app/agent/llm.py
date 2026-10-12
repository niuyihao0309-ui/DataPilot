# [核心] LLM 构建 —— 统一从项目根 .env 读取（当前：硅基流动 SiliconFlow）
# -----------------------------------------------------------------------------
# 合并说明：
#   合并前 deep_agent_demo 从 .env 读模型、data-agent 从 conf/app_config.yaml 读，
#   两处指向不同厂商，容易“改了不生效”。现统一为：**LLM 只认 .env**。
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

# 显式加载项目根目录的 .env（本文件在 app/agent/ 下，向上两级就是项目根）
# 用绝对路径而不是裸 load_dotenv()，避免因启动目录不同而读不到配置
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

# 构建 langchain 模型对象
# 注意：硅基流动的模型名形如 "deepseek-ai/DeepSeek-V4-Flash"，
#      init_chat_model 会按名字前缀自动推断 provider，无需显式传 model_provider。
llm = init_chat_model(
    model=os.getenv("MODEL_NAME"),
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    temperature=0,
)

# 兼容 deepagents 侧的历史命名：
# 合并前的 deep_agent_demo 里，模型变量名叫 model，sub_agents / main_agent 都是
# `from agent.llm import model`。这里保留一个别名，避免改一堆老代码。
model = llm

if __name__ == '__main__':
    for chunk in llm.stream("你是谁?"):
        print(chunk.text, end="")
