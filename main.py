import os
import uuid
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

# 导入我们已经写好的核心业务组件 (把大厨和档案管理员请进来)
from utils.db_handler import load_history, save_history
from agent.react_agent import ReactAgent
from agent.memory_manager import MemoryManager
from agent.tools.agent_tools import resolve_city_from_inputs

# ==========================================
# 1. 初始化 FastAPI 应用 (创建一家名叫“智能客服”的云端餐厅)
# ==========================================
app = FastAPI(
    title="智能客服 Agent API",
    description="前后端分离架构下的工业级大模型 API 接口",
    version="1.0.0"
)

# ==========================================
# 2. 数据模型定义 (Pydantic) - 接口参数的“保安”
# ==========================================
# 规定前端发请求聊天时，必须按照这个格式传数据包过来
class ChatRequest(BaseModel):
    session_id: str  # 当前聊天的会话ID
    query: str       # 用户最新输入的问题
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    client_ip: Optional[str] = None

# 规定返回给前端的会话列表，必须长这个样子
class SessionResponse(BaseModel):
    session_id: str
    title: str
    summary: Optional[str] = "" # 摘要，Optional表示允许为空

# ==========================================
# 3. API 路由设计 - 增删改查 (CRUD) 基础操作
# ==========================================

# @app.get 相当于开通了一个只读的取餐窗口
@app.get("/api/v1/sessions", summary="获取所有会话列表")
async def get_sessions():
    """返回左侧边栏所需的历史会话列表"""
    history = load_history() # 去 MySQL 档案馆拉取所有记录
    
    # 抽取核心信息，拼装成前端渲染列表所需的精简格式
    session_list = [
        {"session_id": sid, "title": data["title"], "summary": data.get("summary", "")}
        for sid, data in history.items()
    ]
    # 倒序排列，确保用户最常聊的、最新的对话排在最上面
    return {"code": 200, "data": list(reversed(session_list))}

# @app.post 相当于开通了一个写入/创建的窗口
@app.post("/api/v1/sessions", summary="新建一个空白会话")
async def create_session():
    """创建一个新的会话，分配 UUID 并落盘"""
    history = load_history()
    new_id = str(uuid.uuid4()) # 后端自动生成一个全球唯一的 ID
    # 搭一个空框架
    history[new_id] = {"title": "新对话", "summary": "", "messages": []}
    save_history(history) # 立刻存入数据库
    # 把新生成的 ID 告诉前端，前端拿到后就可以拿着这个 ID 来发消息了
    return {"code": 200, "data": {"session_id": new_id}}

@app.delete("/api/v1/sessions/{session_id}", summary="删除指定会话")
async def delete_session(session_id: str):
    """删除指定的会话记录及其所有消息"""
    history = load_history()
    if session_id not in history:
        raise HTTPException(status_code=404, detail="会话不存在")
        
    # 从内存字典中删除该会话
    del history[session_id]
    
    # 存回数据库（对于 MySQL 来说，由于 db_handler 中的设计，这会触发外键级联删除）
    save_history(history)
    return {"code": 200, "msg": "删除成功"}

# URL 里的 {session_id} 是动态参数，比如 /api/v1/messages/12345
@app.get("/api/v1/messages/{session_id}", summary="获取某个会话的聊天记录")
async def get_messages(session_id: str):
    """点击左侧边栏时，拉取该会话的所有历史消息渲染到右侧"""
    history = load_history()
    if session_id not in history:
        # 如果前端传来的 ID 数据库里没有，直接抛出 404 错误打回去
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"code": 200, "data": history[session_id]["messages"]}

# ==========================================
# 4. 核心对话与 SSE 流式输出机制 (全场最重要逻辑)
# ==========================================


def extract_client_ip(http_request: Request, request_ip: Optional[str]) -> str:
    """尽量获取真实客户端IP，优先信任前端显式传入，其次读取代理头。"""
    if request_ip:
        return request_ip.strip()

    forwarded_for = http_request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = http_request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()

    if http_request.client and http_request.client.host:
        return http_request.client.host.strip()

    return ""


def build_location_context(chat_request: ChatRequest, client_ip: str) -> tuple[str, str, str]:
    """根据前端传入的位置数据生成高优先级位置说明文本。"""
    resolved_city, source = resolve_city_from_inputs(
        city=chat_request.city,
        longitude=chat_request.longitude,
        latitude=chat_request.latitude,
        client_ip=client_ip,
    )

    if not resolved_city:
        return "", "", ""

    source_mapping = {
        "user_provided_city": "用户主动提供的城市",
        "frontend_coordinates": "前端提供的经纬度",
        "client_ip": "客户端真实IP",
        "server_ip": "服务端出口IP兜底定位",
    }
    source_desc = source_mapping.get(source, "已知位置数据")
    location_text = (
        f"【位置上下文】当前用户所在城市：{resolved_city}。"
        f"该信息来源于{source_desc}，属于高优先级已知事实。"
        "若问题涉及天气或本地环境，请直接基于该城市调用 get_user_weather。"
        "若当前上下文中已经有该城市信息，禁止再调用 get_user_loction 覆盖该城市。"
    )
    return location_text, resolved_city, source


def inject_location_context(messages: list[dict], location_text: str) -> list[dict]:
    """将位置上下文注入到第一条用户消息里，避免额外的 system role 兼容问题。"""
    if not location_text:
        return messages

    injected_messages = []
    injected = False

    for message in messages:
        copied_message = dict(message)
        if not injected and copied_message.get("role") == "user":
            original_content = copied_message.get("content", "")
            copied_message["content"] = f"{location_text}\n\n{original_content}"
            injected = True
        injected_messages.append(copied_message)

    return injected_messages


@app.post("/api/v1/chat/stream", summary="流式对话接口 (SSE)")
async def chat_stream(chat_request: ChatRequest, http_request: Request):
    """
    核心接口：接收用户提问，结合长记忆管理，通过 SSE 流式返回大模型的思考过程
    """
    # 1. 拆解前端传过来的数据包 (通过上面的 Pydantic 保安校验过了，绝对安全)
    session_id = chat_request.session_id
    query = chat_request.query
    client_ip = extract_client_ip(http_request, chat_request.client_ip)
    
    # 2. 从数据库提取历史记忆
    history = load_history()
    if session_id not in history:
        raise HTTPException(status_code=404, detail="会话不存在，请先创建会话")
    session_data = history[session_id]
    
    # 3. 智能重命名：如果是第一次聊天，把用户说的话前15个字当做标题
    if not session_data["messages"]:
        session_data["title"] = query[:15] + ("..." if len(query) > 15 else "")
        
    # 4. 把用户的新问题追加进内存列表
    session_data["messages"].append({"role": "user", "content": query})
    
    # 5. 记忆秘书登场：进行滑动窗口切片与摘要更新
    memory_manager = MemoryManager(window_size=5)
    final_messages, new_summary = memory_manager.process_history(
        session_data["messages"], 
        session_data.get("summary", "")
    )
    location_text, _, _ = build_location_context(chat_request, client_ip)
    agent_messages = inject_location_context(final_messages, location_text)
    
    # 6. 先行落库保存：此时不管大模型等会还不回复，用户的提问和新生成的摘要已经死死存在 MySQL 里了
    session_data["summary"] = new_summary
    save_history(history) 
    
    # 7. 请出大厨 (Agent) 准备做菜
    agent = ReactAgent()

    # 8. 定义 SSE 流式数据生成器 (这是 Python 后端向前端一字一字吐数据的核心)
    def event_stream():
        full_response = "" # 用来在后台偷偷记录大模型完整说了什么
        try:
            # 大厨开始思考，传入的是切片后的精简历史 (final_messages)
            generator = agent.execute_stream(agent_messages)
            
            # 拿到大模型吐出来的一个个字 (chunk)
            for chunk in generator:
                full_response += chunk # 拼接到完整记录里
                
                # 【SSE 协议规范】：必须是 'data: JSON字符串 \n\n' 的格式
                # 前端的 axios 或是 fetch 接收到这种格式，就会知道这是流式数据
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
                
            # 循环结束，告诉前端：“我说完了，你可以关掉加载动画了”
            yield f"data: {json.dumps({'chunk': '[DONE]'}, ensure_ascii=False)}\n\n"
            
        except Exception as e:
            # 容错处理：大模型 API 挂了，把错误信息也通过流返回给前端显示
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            
        finally:
            # 9. 收尾工作：不论中间发生什么，对话结束后都要把 AI 说的话存入数据库
            if full_response:
                # 【高级技巧】：这里必须重新 load 一次。因为流式输出可能耗时 10 秒，
                # 这 10 秒内别人可能修改了别的对话。如果用旧的 history 覆盖，会造成数据丢失。
                latest_history = load_history()
                latest_history[session_id]["messages"].append({"role": "assistant", "content": full_response})
                save_history(latest_history)

    # 10. 使用 FastAPI 专用的 StreamingResponse，将生成器挂载到响应上发送给前端
    return StreamingResponse(event_stream(), media_type="text/event-stream")

# ==========================================
# 5. 服务启动入口
# ==========================================
if __name__ == "__main__":
    import uvicorn
    # uvicorn 是跑在 Python 和网络接口之间的高性能网关
    # reload=True 意思是只要你修改了代码，服务器会自动热重启，极其方便调试
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
