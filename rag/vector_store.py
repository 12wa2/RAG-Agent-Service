import os
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
# 核心检索组件
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever

from utils.config_handler import chroma_conf
from model.factory import embed_model
from utils.path_tool import get_abs_path
from utils.file_handler import pdf_loader, txt_loader, listdir_with_allowed_type, get_file_md5_hex
from utils.logger_handler import logger


class VectStoreService:
    def __init__(self):
        # 1. 初始化向量数据库 (Chroma 会自动读取持久化目录)
        self.vector_store = Chroma(
            collection_name=chroma_conf["collection_name"],
            embedding_function=embed_model,
            persist_directory=chroma_conf["persist_directory"]
        )

        # 2. 初始化分词器
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )

        # 3. 核心：启动时自动同步 BM25 检索器
        self.bm25_retriever = self._sync_bm25_from_chroma()

    def _sync_bm25_from_chroma(self):
        """
        【函数功能】：从硬盘的 Chroma 数据库中提取所有文本，重建内存中的 BM25 索引。
        这是为了解决程序重启后，BM25 索引丢失的问题。
        """
        try:
            # 1. 从 Chroma 中抓取所有数据
            # .get() 会返回一个字典，包含所有文档的 ['ids', 'documents', 'metadatas']
            # 注意：这里拿出来的 documents 只是纯字符串列表
            all_data = self.vector_store.get()

            # 2. 安全检查：判断库里到底有没有数据
            # 如果 all_data 为空，或者 ['documents'] 列表长度为 0，说明知识库是空的
            if all_data and all_data['documents']:
                docs = []

                # 3. 数据格式转换（核心步骤）
                # Chroma 给我们的是分开的列表（文本列表、元数据列表）
                # 但 LangChain 的检索器需要的是包装好的 Document 对象列表
                # 我们在这里用循环把它们“重新打包”
                for i in range(len(all_data['documents'])):
                    new_doc = Document(
                        page_content=all_data['documents'][i],  # 填充文本内容
                        metadata=all_data['metadatas'][i] if all_data['metadatas'] else {}  # 填充来源、页码等元数据
                    )
                    docs.append(new_doc)

                # 4. 打印进度日志
                # 让开发者知道系统已经成功从硬盘里捞回了多少条数据
                logger.info(f"[Hybrid RAG] 成功同步 {len(docs)} 条存量数据至 BM25 索引")

                # 5. 实例化 BM25 检索器
                # 这是最消耗 CPU 的一步，它会在内存中计算 326 条数据的词频和权重
                # 计算完成后，bm25_retriever 就可以直接用来搜索关键词了
                return BM25Retriever.from_documents(docs)

            # 如果库里没数据，返回 None，外层代码会据此判断是否只启用向量检索
            return None

        except Exception as e:
            # 5. 异常处理
            # 即使同步失败（比如权限问题或内存溢出），也只是记录错误，不要让整个程序崩溃
            logger.error(f"[Hybrid RAG] 同步 BM25 失败: {e}")
            return None

    def get_retriever(self):
        """生成并返回混合检索器"""
        # 获取基础向量检索器
        vector_retriever = self.vector_store.as_retriever(search_kwargs={"k": chroma_conf["k"]})

        # 如果 BM25 还没数据，先退化为纯向量检索
        if not self.bm25_retriever:
            logger.warning("[检索系统] BM25 为空，当前仅使用向量检索")
            return vector_retriever

        # 返回 50/50 混合检索器
        logger.info("[检索系统] 混合检索模式(Vector + BM25)已激活")
        return EnsembleRetriever(
            retrievers=[self.bm25_retriever, vector_retriever],
            weights=[0.5, 0.5]
        )

    # --- 数据加载辅助方法 ---
    def _check_md5_hex(self, md5_for_check: str):
        md5_path = get_abs_path(chroma_conf["md5_hex_store"])
        if not os.path.exists(md5_path):
            open(md5_path, "w", encoding="utf-8").close()
            return False
        with open(md5_path, "r", encoding="utf-8") as f:
            return md5_for_check in [line.strip() for line in f.readlines()]

    def _save_md5_hex(self, md5_for_check: str):
        md5_path = get_abs_path(chroma_conf["md5_hex_store"])
        with open(md5_path, "a", encoding="utf-8") as f:
            f.write(md5_for_check + "\n")

    def _get_file_documents(self, read_path: str):
        if read_path.lower().endswith(".txt"): return txt_loader(read_path)
        if read_path.lower().endswith(".pdf"): return pdf_loader(read_path)
        return []

    def load_documents(self):
        """读取数据文件夹，去重并存入库"""
        allowed_files_path = listdir_with_allowed_type(
            get_abs_path(chroma_conf["data_path"]),
            tuple(chroma_conf["allow_knowledge_file_type"])
        )

        new_docs_added = False
        for path in allowed_files_path:
            md5_hex = get_file_md5_hex(path)
            if self._check_md5_hex(md5_hex):
                logger.info(f"[加载知识库] {os.path.basename(path)} 已存在，跳过")
                continue

            try:
                raw_docs = self._get_file_documents(path)
                if not raw_docs: continue

                split_docs = self.spliter.split_documents(raw_docs)
                self.vector_store.add_documents(split_docs)
                self._save_md5_hex(md5_hex)
                new_docs_added = True
                logger.info(f"[加载知识库] {os.path.basename(path)} 加载成功")
            except Exception as e:
                logger.error(f"[加载知识库] {path} 失败: {e}", exc_info=True)

        # 关键：如果有新文件，重新构建 BM25 以包含最新内容
        if new_docs_added:
            self.bm25_retriever = self._sync_bm25_from_chroma()


if __name__ == "__main__":
    vs = VectStoreService()
    vs.load_documents()
    test_res = vs.get_retriever().invoke("扫地机器人维护")
    for r in test_res:
        print(f"内容: {r.page_content[:50]}...\n{'-' * 20}")