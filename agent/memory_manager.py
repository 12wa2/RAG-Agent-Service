from model.factory import chat_model
# ✅ 新版写法（换成这个）
from langchain_core.messages import HumanMessage, SystemMessage

class MemoryManager:
    def __init__(self, window_size=5):
        """
        初始化记忆管理器：设定大脑的“短期记忆”容量
        :param window_size: 滑动窗口大小（保留最近的几轮对话，一轮包含 user 和 assistant）
        """
        # 【关键换算】：一轮对话包含“用户问”和“AI答”2条消息。
        # 如果你想保留最近 5 轮对话，实际上就是保留列表里最后的 10 条消息。
        self.max_recent_messages = window_size * 2 
        
        # 借用你工厂里定义好的大模型实例，用来执行后面的“写摘要”任务
        self.llm = chat_model

    def _summarize_messages(self, messages_to_summarize: list, previous_summary: str = "") -> str:
        """
        核心机制一：摘要压缩（把长篇大论缩写成小纸条）
        将那些“被挤出窗口”的旧消息，浓缩成简短的摘要。
        """
        # 防御性编程：如果没有需要压缩的消息（比如刚好没超限），直接把旧摘要原样退回
        if not messages_to_summarize:
            return previous_summary

        # 1. 拼装原材料：把字典格式的对话 [{"role":"user", "content":"你好"}] 
        # 转换成大白话纯文本："user: 你好\nassistant: 您好！" 方便大模型阅读
        chat_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages_to_summarize])
        
        # 2. 构造指令 (Prompt)：告诉大模型它现在不是客服，而是“总结专员”
        prompt = "你是一个专业的信息总结助手。请将以下用户和智能客服的对话历史进行高度浓缩，提取出用户的核心特征、偏好、遇到的问题以及已经给出的解决方案。保持客观、简练。"
        
        # 3. 记忆滚雪球：如果以前已经有过摘要了，必须把旧摘要也喂给模型，
        # 让它把【老摘要】和【刚刚过期的对话】揉在一起，写出一份【最新摘要】。
        if previous_summary:
            prompt += f"\n\n这里是之前的对话摘要，请结合新的对话内容，输出一份整合后的最新摘要：\n{previous_summary}"
            
        prompt += f"\n\n新的对话历史：\n{chat_text}\n\n请输出最新的摘要："

        try:
            # 4. 调用大模型：真正执行总结任务，并把结果前后空格去掉后返回
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception as e:
            # 5. 容错处理：如果调用 API 失败（断网、超时等），千万不能返回空字符串！
            # 宁可这次不总结，也要把旧摘要还回去，保证以前的记忆不丢。
            print(f"摘要生成失败: {e}")
            return previous_summary

    def process_history(self, full_messages: list, current_summary: str = "") -> tuple[list, str]:
        """
        核心机制二：滑动窗口（海关安检员）
        处理全量的历史消息，将其分割为“需要压缩的旧消息”和“留在窗口内的新消息”
        :return: (精简后可直接传给Agent的消息列表, 最新的摘要文本)
        """
        # 场景A：记录很少，还没撑破窗口。
        # 比如 max 是 10 条，现在才聊了 6 条。直接放行，不触发总结。
        if len(full_messages) <= self.max_recent_messages:
            return full_messages, current_summary

        # 场景B：记录超限，触发滑动与压缩机制！
        
        # 1. 截断 (保留新记忆)：从全量列表中，切片保留最后 N 条消息。
        # 比如 full_messages 有 15 条，max_recent_messages 是 10，这里就留下第 6 到 15 条。
        recent_messages = full_messages[-self.max_recent_messages:]
        
        # 2. 剥离 (挑出老记忆)：把被挤出窗口的那部分拿出来。
        # 也就是上面例子中的第 1 到 5 条。这些马上要被送去压缩了。
        messages_to_compress = full_messages[:-self.max_recent_messages]

        # 3. 压缩 (召唤总结专员)：把老记忆和当前摘要传给上面的 _summarize_messages 函数，拿到新摘要。
        new_summary = self._summarize_messages(messages_to_compress, current_summary)

        

        # 4. 拼装公文包 (Context Injection)：准备发给大模型的最终内容
        final_messages = []
        
        # 如果有摘要，就把摘要伪装成一条 System 消息，悄悄塞在最前面。
        # 相当于给 AI 贴了一张便签：“回答问题前，先看一眼以前的总结”。
        if new_summary:
            final_messages.append({
                "role": "system", 
                "content": f"【历史对话摘要记忆】：{new_summary}\n(请结合以上摘要回答用户的最新问题)"
            })
            
        # 把刚才截断留下来的“最近几轮原始对话”追加在摘要后面。
        final_messages.extend(recent_messages)

        # 返回两样东西：
        # final_messages: 给接下来的 Agent 回答问题用（省 Token！）
        # new_summary: 给你拿去存入 MySQL 的 sessions 表用（持久化！）
        return final_messages, new_summary