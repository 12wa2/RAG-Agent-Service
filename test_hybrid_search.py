import os
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
# 👇 真正的终极修复：官方把混合检索器剥离到了 classic 包里
from langchain_classic.retrievers import EnsembleRetriever

# ⚠️ 填入你自己的阿里云 API KEY
os.environ["DASHSCOPE_API_KEY"] = "sk-f749224e7b2749839626e8b24167a761"

# 1. 模拟你的说明书知识库片段
doc_list = [
    "【常见问题】如果机器人在清扫时原地打转，可能是底部的悬崖传感器被灰尘遮挡，请用干布擦拭。",
    "【故障说明】Zhongqing PM01 型号设备如出现 E-104 报错，代表主刷被异物卡死，请切断电源后清理主刷毛发。",
    "【保养建议】建议每个月清洗一次尘盒与滤网，并在完全晾干后装回机器，以保持吸力。",
    "【故障说明】如果你听到咔咔异响，说明刷子可能缠绕了头发或者电线，需要立刻停机检查。"
]

# --------------------------------------------------
# 🧠 “左脑”：建立基于语义的 Chroma 向量检索 (Vector Store)
# --------------------------------------------------
print("正在构建向量数据库...")
embeddings = DashScopeEmbeddings()
# 把文本存入内存级别的 Chroma
vectorstore = Chroma.from_texts(doc_list, embedding=embeddings)
# 设置向量检索器，每次找回最相似的 2 条
chroma_retriever = vectorstore.as_retriever(search_kwargs={"k": 2})


# --------------------------------------------------
# 🧠 “右脑”：建立基于关键词字面匹配的 BM25 检索
# --------------------------------------------------
print("正在构建 BM25 关键词索引...")
bm25_retriever = BM25Retriever.from_texts(doc_list)
# 设置 BM25 每次也找回 2 条
bm25_retriever.k = 2


# --------------------------------------------------
# 🤝 终极融合：构建 EnsembleRetriever (混合检索器)
# --------------------------------------------------
# weights=[0.5, 0.5] 表示向量检索和关键词检索的权重各占一半
hybrid_retriever = EnsembleRetriever(
    retrievers=[bm25_retriever, chroma_retriever],
    weights=[0.5, 0.5]
)

# --------------------------------------------------
# 🔍 开始测试！
# --------------------------------------------------
# 测试一个带有极强特征的专有名词和故障码
query = "我的 Zhongqing PM01 扫地机一直报 E-104，怎么办？"
print(f"\n用户提问: {query}")

# 1. 如果只用向量检索（可能会被“异响”、“打转”等语义相似但型号不对的文本干扰）
print("\n--- [左脑] 纯 Chroma 向量检索结果 ---")
vector_results = chroma_retriever.invoke(query)
for i, doc in enumerate(vector_results):
    print(f"[{i+1}] {doc.page_content}")

# 2. 如果只用 BM25（对 PM01、E-104 这种字眼极其敏感）
print("\n--- [右脑] 纯 BM25 关键词检索结果 ---")
bm25_results = bm25_retriever.invoke(query)
for i, doc in enumerate(bm25_results):
    print(f"[{i+1}] {doc.page_content}")

# 3. 混合检索（兼顾两者，通过 RRF 算法重新打分）
print("\n--- 🌟 [全脑] Hybrid 混合检索最终结果 ---")
hybrid_results = hybrid_retriever.invoke(query)
for i, doc in enumerate(hybrid_results):
    print(f"[{i+1}] {doc.page_content}")