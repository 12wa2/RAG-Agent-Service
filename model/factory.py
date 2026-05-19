from abc import ABC, abstractmethod
from typing import Optional
from langchain.embeddings import Embeddings
from langchain_community.chat_models.tongyi import BaseChatModel
from utils.config_handler import rag_conf
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.document_compressors.dashscope_rerank import DashScopeRerank # 导入重排器
import os # 导入环境变量模块

try:
    from langchain_openai import ChatOpenAI # [新增] 导入 OpenAI 兼容接口，用于连接本地 LLaMA-Factory
except ImportError:
    ChatOpenAI = None
class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass


class ChatModelFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return ChatTongyi(model=rag_conf["chat_model_name"])

class AgentChatModelFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        if ChatOpenAI is None:
            return None

        # 读取智能体专属模型
        model_name = rag_conf.get("agent_chat_model_name", "rabbit_qwen")
        api_base = rag_conf.get("agent_chat_api_base", "http://localhost:6006/v1")
        
        # LLaMA-Factory 启动的 API 默认兼容 OpenAI 格式
        # api_key 可以随便填一个非空的字符串，因为本地一般不校验
        return ChatOpenAI(
            model=model_name,
            openai_api_base=api_base,
            openai_api_key="EMPTY", 
            temperature=0.0
            # 注意：此处千万不能加 streaming=True，否则 LLaMA-Factory 在调用工具时会崩溃
        )

class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return DashScopeEmbeddings(model=rag_conf["embedding_model_name"])

class ReRankModelFactory(BaseModelFactory):
    def generator(self) -> Optional[DashScopeRerank]:
        """
        生成阿里云重排模型实例
        注意：这里返回的是 DashScopeRerank 对象，而不是 Embeddings
        """
        return DashScopeRerank(
            model=rag_conf["rerank_model_name"],
        )

chat_model = ChatModelFactory().generator()
agent_chat_model = AgentChatModelFactory().generator() # [新增] 生成智能体专属的模型实例
embed_model = EmbeddingsFactory().generator()
rerank_model = ReRankModelFactory().generator()
