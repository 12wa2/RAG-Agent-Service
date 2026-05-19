"""
总结服务类：用户提问，搜索参考资料，将提问和参考资料提交给模型，让模型总结回复
"""
import os
from itertools import chain
from langchain_core.documents import Document

# 从工厂导入已经生产好的实例：聊天模型、重排模型
from model.factory import chat_model, rerank_model
from utils.prompt_loader import load_rag_prompts
from rag.vector_store import VectStoreService
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from utils.logger_handler import logger
from utils.config_handler import rag_conf

class RagSummarizeService(object):
    def __init__(self):
        # 1. 初始化向量库服务
        self.vector_store = VectStoreService()

        # 2. 获取混合检索器 (Vector + BM25)
        self.retriver = self.vector_store.get_retriever()

        # 3. 【核心修改】：直接从工厂拿到重排引擎实例 (DashScopeRerank 对象)
        self.rerank_engine = rerank_model

        self.prompt_text = load_rag_prompts()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.model = chat_model
        self.chain = self._init_chain()

    def _init_chain(self):
        # 构建核心 LLM 链条
        chain = self.prompt_template | self.model | StrOutputParser()
        return chain

    def retriever_docs(self, query: str) -> list[Document]:
        """第一阶段：粗排检索（获取 10-15 条候选资料）"""
        return self.retriver.invoke(query)

    def _rerank_docs(self, query: str, docs: list[Document], top_n: int = 5) -> list[Document]:
        """
        第二阶段：精排重排
        利用工厂生成的 rerank_engine 调用 compress_documents 方法
        """
        if not docs:
            return []

        try:
            # 【核心修改】：一行代码搞定！
            # 它会自动提取 docs 里的文字，发送给阿里云重排，并按分数重新排序返回 Document 对象
            reranked_docs = self.rerank_engine.compress_documents(
                query=query,
                documents=docs
            )

            # 取出重排后的前 top_n 名
            final_docs = reranked_docs[:top_n]

            logger.info(f"[Rerank完成] 已利用 DashScopeRerank 精选出 {len(final_docs)} 条最优片段")
            return final_docs

        except Exception as e:
            # 容错处理：如果重排挂了，直接返回粗排的前 top_n 条，保证业务不中断
            logger.error(f"[Rerank异常] 自动降级至粗排结果，错误信息: {str(e)}")
            return docs[:top_n]

    def _format_context(self, docs: list[Document]) -> str:
        context = ""
        counter = 0
        for doc in docs:
            counter += 1
            # 备注：DashScopeRerank 默认会将分数存在 metadata 的 'relevance_score' 中
            score = doc.metadata.get("relevance_score", "N/A")
            context += f"【参考资料{counter}】(相关度:{score}): {doc.page_content}\n"
        return context

    def build_context(self, query: str, use_rerank: bool = True, top_n: int = 5) -> tuple[str, list[Document]]:
        # 第一级火箭：混合检索（粗排）
        initial_docs = self.retriever_docs(query)

        # 第二级火箭：按需执行精排
        if use_rerank:
            context_docs = self._rerank_docs(query, initial_docs, top_n=top_n)
        else:
            context_docs = initial_docs[:top_n]

        return self._format_context(context_docs), context_docs

    def answer_with_context(self, query: str, use_rerank: bool = True, top_n: int = 5) -> tuple[str, str]:
        context, _ = self.build_context(query, use_rerank=use_rerank, top_n=top_n)

        # 第三级火箭：大模型生成总结
        answer = self.chain.invoke(
            {
                "input": query,
                "context": context,
            }
        )
        return answer, context

    def rag_summarize(self, query: str) -> str:
        answer, _ = self.answer_with_context(query, use_rerank=True, top_n=5)
        return answer

if __name__ == "__main__":
    rag = RagSummarizeService()
    # 测试：针对 PM01 这种具体的型号问题，重排效果最明显
    print(rag.rag_summarize("我的扫地机器人 PM01 经常报 E-104 错误该怎么解决？"))
