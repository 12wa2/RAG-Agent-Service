# ---------------------------------------------------------
# 1. 引入需要的工具包
# ---------------------------------------------------------
import os        # 操作系统工具箱，用来处理文件夹和路径
import time      # 时间工具箱，等会儿用来做“打字机”停顿效果
import json      # JSON 解析器，用来把字符串变回 Python 字典
import requests  # 【核心】网络请求库，相当于前端的“手机”，专门用来给 FastAPI 后端打电话

import streamlit as st # 画网页界面的核心库
from utils.config_handler import chroma_conf  # 导入配置，比如允许上传什么文件
from utils.path_tool import get_abs_path      # 导入路径工具，找准文件存在哪
from rag.vector_store import VectStoreService # 导入知识库处理服务

# ---------------------------------------------------------
# 2. 告诉前端：你的后端老板在哪？
# ---------------------------------------------------------
# 这个地址就是你刚才在浏览器里看到的 FastAPI 地址
# 前端所有的请求，都要发往这个根地址
API_BASE_URL = "http://127.0.0.1:8000/api/v1"

# ---------------------------------------------------------
# 3. 封装三个“打电话”动作 (专门和 FastAPI 沟通)
# ---------------------------------------------------------

# 动作 1：获取所有的历史会话列表
def fetch_sessions():
    try:
        # 用 GET 方式访问后端的 /sessions 接口（相当于查询）
        res = requests.get(f"{API_BASE_URL}/sessions")
        # 200 代表网络请求成功
        if res.status_code == 200:
            # 把后端返回的 JSON 数据拿出来，提取里面的 "data" 列表
            return res.json().get("data", [])
    except Exception as e:
        # 如果后端没启动或者报错，在侧边栏弹个红色警告
        st.sidebar.error(f"无法连接后端: {e}")
    return [] # 如果失败了，返回空列表，防止程序崩溃

# 动作 2：告诉后端，给我建一个新会话
def create_new_session():
    try:
        # 用 POST 方式访问 /sessions 接口（相当于创建新东西）
        res = requests.post(f"{API_BASE_URL}/sessions")
        if res.status_code == 200:
            # 去深入解析返回的数据：获取里面的 session_id 字符串
            return res.json().get("data", {}).get("session_id")
    except Exception:
        pass
    return None

# 动作 3：告诉后端，我要查某个特定 ID 的所有聊天记录
def fetch_messages(session_id):
    try:
        # 用 GET 方式，把 ID 拼在网址后面发过去，比如 /messages/1234
        res = requests.get(f"{API_BASE_URL}/messages/{session_id}")
        if res.status_code == 200:
            # 返回这段对话所有的聊天记录列表
            return res.json().get("data", [])
    except Exception:
        pass
    return []

# ---------------------------------------------------------
# 4. 开始画网页主界面
# ---------------------------------------------------------
st.title("智扫通机器人智能客服") # 在网页正中间写个大标题
st.divider() # 画一条灰色的横线，为了美观

# ---------------------------------------------------------
# 5. 网页状态管理 (确定我现在到底在看哪个对话)
# ---------------------------------------------------------

# 刚打开网页时，先给后端打个电话，把所有历史会话名单拉过来
sessions_list = fetch_sessions()

# 如果发现名单是空的（比如第一次用）
if not sessions_list:
    new_id = create_new_session() # 让后端赶紧新建一个
    if new_id:
        sessions_list = fetch_sessions() # 新建完后，重新拉取一次名单

# 如果网页缓存里没有“当前会话ID”，就默认选中名单里的第一个
if "current_session_id" not in st.session_state and sessions_list:
    st.session_state["current_session_id"] = sessions_list[0]["session_id"]

# 防御措施：检查当前选中的 ID，到底还在不在后端的名单里（防止被别人删了）
if sessions_list:
    # 提取出所有的合法 ID 列表
    valid_ids = [s["session_id"] for s in sessions_list]
    # 如果当前 ID 不合法了，强行把它掰回合法名单的第一个
    if st.session_state.get("current_session_id") not in valid_ids:
         st.session_state["current_session_id"] = valid_ids[0]

# 把当前合法的 ID 存到一个短变量里，方便下面用
current_id = st.session_state.get("current_session_id")
# 给后端打电话，把当前这个 ID 里面聊过的所有天拉出来
current_messages = fetch_messages(current_id) if current_id else []

# ---------------------------------------------------------
# 6. 开始画左侧的侧边栏
# ---------------------------------------------------------
with st.sidebar:
    st.header("会话管理") # 侧边栏标题
    col1, col2 = st.columns(2) # 把侧边栏分成左右两列放按钮
    
    # 在左列放一个“新建会话”按钮
    if col1.button("新建会话", use_container_width=True):
        new_sid = create_new_session() # 让后端建新会话
        if new_sid:
            st.session_state["current_session_id"] = new_sid # 选中新生成的这个
            st.rerun() # 强制刷新整个网页，让新会话显示出来
        
    # 在右列放一个按钮（暂时禁用它）
    if col2.button("删除功能暂未实现", use_container_width=True, disabled=True):
        pass

    st.write("历史会话") # 写一行小字
    # 遍历刚才从后端拉过来的会话名单
    for session_data in sessions_list:
        sid = session_data["session_id"] # 拿到这个会话的 ID
        title = session_data["title"]    # 拿到这个会话的名字
        
        # 如果正好是当前选中的，就在名字前面加个小手势 👉
        btn_label = f"👉 {title}" if sid == current_id else title
        
        # 画出这个按钮，只要用户点击了它
        if st.button(btn_label, key=f"btn_{sid}", use_container_width=True):
            st.session_state["current_session_id"] = sid # 就把当前 ID 切换成它
            st.rerun() # 刷新网页，右边就会立刻显示这个对话的内容
            
    st.divider() # 画横线

    # --- 知识库上传模块 ---
    st.header("知识库管理")
    st.write("上传文档并自动更新到向量库。")
    allowed_types = chroma_conf.get("allow_knowledge_file_type", ["txt", "pdf"])
    # 召唤一个文件上传框，允许传多份文件
    uploaded_files = st.file_uploader("选择要上传的本地文档", type=allowed_types, accept_multiple_files=True)
    
    # 知识库这里的代码没变，还是让前端直接存进硬盘里并做向量化
    if st.button("上传并添加到知识库", use_container_width=True):
        if uploaded_files:
            with st.spinner("正在处理文档并构建向量索引..."):
                data_dir = get_abs_path(chroma_conf["data_path"])
                if not os.path.exists(data_dir):
                    os.makedirs(data_dir)
                saved_files = []
                for file in uploaded_files:
                    file_path = os.path.join(data_dir, file.name)
                    with open(file_path, "wb") as f:
                        f.write(file.getbuffer())
                    saved_files.append(file.name)
                try:
                    vs = VectStoreService()
                    vs.load_documents()
                    st.success(f"成功上传并处理了 {len(saved_files)} 个文档！")
                except Exception as e:
                    st.error(f"处理失败: {str(e)}")
        else:
            st.warning("请先选择要上传的文件！")

# ---------------------------------------------------------
# 7. 右侧主聊天区：渲染过往记录
# ---------------------------------------------------------
# 遍历从后端拉过来的当前对话所有内容
for message in current_messages:
    # 根据角色（user 还是 assistant）画头像，并把话写在旁边
    st.chat_message(message["role"]).write(message["content"])

# ---------------------------------------------------------
# 8. 最底部的输入框：接客与网络流解析 (全场最难的地方)
# ---------------------------------------------------------
# 在底部画一个聊天输入框，等待用户打字回车
prompt = st.chat_input()

# 如果用户按了回车，而且当前有合法的会话 ID
if prompt and current_id:
    # 先立刻把用户刚刚打出来的字，画到屏幕上
    st.chat_message("user").write(prompt)

    # 显示“智能客服思考中”的圈圈动画
    with st.spinner("智能客服思考中..."):
        
        # 这是一个【生成器函数】，用来一点点接住后端吐出来的字
        def fetch_sse_stream():
            # 拼装请求网址：http://127.0.0.1:8000/api/v1/chat/stream
            url = f"{API_BASE_URL}/chat/stream"
            # 组装要发给后端的包裹：告诉后端“我是哪个对话”，以及“我问了啥”
            payload = {"session_id": current_id, "query": prompt}
            
            # 向后端发请求。stream=True 是灵魂！意思是：建立长连接，慢慢接数据，不要挂电话！
            with requests.post(url, json=payload, stream=True) as response:
                
                # 开始在履带上接包裹。iter_lines() 意思是：后端每发来一行，就拿下来看一眼
                for line in response.iter_lines():
                    # 如果这一行不是空的
                    if line:
                        # 收到的网络数据是乱码（二进制），先用 utf-8 翻译成文本
                        decoded_line = line.decode('utf-8')
                        
                        # 检查这行文本是不是以 "data: " 打头（因为 SSE 协议规定必须这么写）
                        if decoded_line.startswith("data: "):
                            # 把开头的 "data: " 砍掉（切片从第 6 个字符开始），只留下核心的 JSON 数据
                            data_str = decoded_line[6:] 
                            
                            try:
                                # 把字符串变回 Python 认得的字典格式
                                data_json = json.loads(data_str)
                                
                                # 容错：看看后端是不是发来了错误信息（比如 API 挂了）
                                if "error" in data_json:
                                    # 如果报错了，把错误吐给界面，然后强行跳出循环结束
                                    yield f"\n\n**[Error]** {data_json['error']}"
                                    break
                                    
                                # 核心：把字典里的 "chunk"（也就是那个单一的字）掏出来
                                chunk = data_json.get("chunk")
                                
                                # 判断：如果后端发来的是 "[DONE]"，说明他说完再见了
                                if chunk == "[DONE]":
                                    break # 打破循环，关电话
                                
                                # 如果有字发过来
                                elif chunk:
                                    # 把这个字拆开，停顿 0.01 秒，再吐出去，制造打字机感
                                    for char in chunk:
                                        time.sleep(0.01)
                                        yield char # yield 就像吐泡泡，吐出去一个字给界面
                            except json.JSONDecodeError:
                                # 如果解析 JSON 失败了（比如网络卡顿数据残缺），就装作没看见，接着等下一个包
                                pass 

        # 在屏幕上画一个机器人的头像，用 st.write_stream 去接住上面那个函数吐出来的“泡泡”（文字）
        st.chat_message("assistant").write_stream(fetch_sse_stream())

        # 当上面那个框写完字后，代码走到这里。强行刷新网页一次！
        # 为什么要刷新？因为此时最新记录已经存在后端了。
        # 网页一刷新，第一步的 fetch_messages() 就会再次执行，把完整的聊天记录重新从后端拉回来画一遍。
        st.rerun()