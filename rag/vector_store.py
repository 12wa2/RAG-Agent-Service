from langchain_chroma import Chroma
from langchain_core.documents import Document
from utils.config_handler import chroma_conf
from model.factory import embed_model
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.path_tool import get_abs_path
from utils.file_handler import pdf_loader, txt_loader, listdir_with_allowed_type, get_file_md5_hex
from utils.logger_handler import logger
import os


#  新增：混合检索必备包
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever

class VectStoreService:
    def __init__(self):
        # 1. 初始化向量数据库 (修复双目录 Bug：强制使用基于项目根目录的绝对路径)
        self.vector_store = Chroma(
            collection_name = chroma_conf["collection_name"],
            embedding_function = embed_model,
            persist_directory = get_abs_path(chroma_conf["persist_directory"])
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size = chroma_conf["chunk_size"],
            chunk_overlap = chroma_conf["chunk_overlap"],
            separators = chroma_conf["separators"],
            length_function = len,
        )
        
        # 2. 初始化 BM25 检索器（关键步骤）
        self.bm25_retriever = self._init_bm25_from_chroma()

    def _init_bm25_from_chroma(self):
        """
        从现有的 Chroma 向量库中提取所有文档来初始化 BM25。
        解决向量库持久化但 BM25 内存化的问题。
        """
        try:
            # 从 Chroma 中获取所有已有文档
            all_docs = self.vector_store.get()
            if all_docs and all_docs['documents']:
                documents = []
                for i in range(len(all_docs['documents'])):
                    doc = Document(
                        page_content=all_docs['documents'][i],
                        metadata=all_docs['metadatas'][i] if all_docs['metadatas'] else {}
                    )
                    documents.append(doc)
                
                logger.info(f"[混合检索] 成功从向量库同步 {len(documents)} 条数据到 BM25")
                return BM25Retriever.from_documents(documents)
            else:
                # 如果库里还是空的，先给一个空的占位（后续 load 时再更新）
                logger.warning("[混合检索] 向量库目前为空，BM25 暂未初始化数据")
                return None
        except Exception as e:
            logger.error(f"[混合检索] 初始化 BM25 失败: {str(e)}")
            return None


    def get_retriever( self ):
        """
        返回混合检索器：将向量检索与关键词检索 1:1 融合
        """
        # 向量检索器
        vector_retriever = self.vector_store.as_retriever(search_kwargs={"k": chroma_conf["k"]})
        
        # 如果 BM25 还没初始化（说明是第一次运行且没存数据），则退化回纯向量检索
        if self.bm25_retriever is None:
            return vector_retriever
            
        # 混合检索：50% 语义 + 50% 关键词
        logger.info("[检索系统] 已激活 Hybrid Search 模式")
        return EnsembleRetriever(
            retrievers=[self.bm25_retriever, vector_retriever],
            weights=[0.5, 0.5]
        )


    def load_documents( self ):
            """
            从数据文件夹内读取数据文件，转为向量存入向量库
            要计算文件的MD5做去重
            ：return:None
            """
            def check_md5_hex(md5_for_check:str):
                if not os.path.exists(get_abs_path(chroma_conf["md5_hex_store"])):
                    # 创建文件
                    open(get_abs_path(chroma_conf["md5_hex_store"]), "w", encoding="utf-8").close()
                    return False

                with open(get_abs_path(chroma_conf["md5_hex_store"]), "r", encoding="utf-8") as f:
                    for line in f.readlines():
                        line = line.strip()
                        if line == md5_for_check:
                            return True        # md5处理过

                    return False      # md5 没处理过


            def save_md5_hex(md5_for_check:str):
                with open(get_abs_path(chroma_conf["md5_hex_store"]), "a", encoding="utf-8") as f:
                    f.write(md5_for_check + "\n")


            def get_file_documents(read_path: str):
                if read_path.endswith("txt"):
                    return txt_loader(read_path)

                if read_path.endswith("pdf"):
                    return pdf_loader(read_path)

                return []



            allowed_files_path: list[str] = listdir_with_allowed_type(
                get_abs_path(chroma_conf["data_path"]),
                tuple(chroma_conf["allow_knowledge_file_type"])
            )


            for path in allowed_files_path:
                # 获取文件的MD5
                md5_hex = get_file_md5_hex(path)

                if check_md5_hex(md5_hex):
                    logger.info(f"[加载知识库]{path}内容已经存在知识库内，跳过")
                    continue

                try:
                    documents: list[str] = get_file_documents(path)

                    if not documents:
                        logger.warning(f"[加载知识库]{path}内容为空，跳过")
                        continue

                    split_documents: list[Document] = self.spliter.split_documents(documents)

                    if not split_documents:
                        logger.warning(f"[加载知识库]{path}分片后没有有效文本内容，跳过")
                        continue

                    # 将内容存入向量库
                    self.vector_store.add_documents(split_documents)

                    # 记录这个已经处理好的文件md5,避免下次重复加载
                    save_md5_hex(md5_hex)

                    logger.info(f"[加载知识库]{path}内容加载成功")

                except Exception as e:
                    # exc_info为True会记录详细的报错堆栈，如果为False仅记录报错信息本身
                    logger.error(f"[加载知识库]{path}内容加载失败：{str(e)}", exc_info=True)
                    continue


if __name__ == "__main__":
    vs = VectStoreService()
    vs.load_documents()

    retriever = vs.get_retriever()

    res = retriever.invoke("迷路")
    for r in res:
        print(r.page_content)
        print("-" * 20)



