from abc import ABC, abstractmethod
from typing import Optional
from langchain.embeddings import Embeddings
from langchain_community.chat_models.tongyi import BaseChatModel
from utils.config_handler import rag_conf
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.document_compressors.dashscope_rerank import DashScopeRerank # 导入重排器
import os # 导入环境变量模块
class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass


class ChatModelFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        return ChatTongyi(model=rag_conf["chat_model_name"])


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
embed_model = EmbeddingsFactory().generator()
rerank_model = ReRankModelFactory().generator()
