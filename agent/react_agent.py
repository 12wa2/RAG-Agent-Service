from model.factory import agent_chat_model
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import (rag_summarize, get_user_weather, get_user_loction, get_user_id,
                                     get_current_month, fetch_external_data, fill_context_for_report)
from agent.tools.middleware import monitor_tool, log_before_model, report_prompt_switch

class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model = agent_chat_model, # 使用你微调的专属模型
            system_prompt = load_system_prompts(),
            tools = [rag_summarize, get_user_weather, get_user_loction, get_user_id,
                     get_current_month, fetch_external_data, fill_context_for_report],
            middleware = [monitor_tool, log_before_model, report_prompt_switch],
        )

    @staticmethod
    def _normalize_content(content) -> str:
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            return "".join(text_parts).strip()

        return ""

    @staticmethod
    def _looks_like_tool_call_text(text: str) -> bool:
        lowered = text.lower()
        return (
            lowered.startswith('{"name"')
            or ('"name"' in lowered and '"arguments"' in lowered)
            or "tool_call" in lowered
        )

    def _extract_user_visible_text(self, message) -> str:
        if not isinstance(message, AIMessage):
            return ""

        if getattr(message, "tool_calls", None):
            return ""

        text = self._normalize_content(message.content)
        if not text or self._looks_like_tool_call_text(text):
            return ""

        return text + "\n"

    def execute_stream(self, messages: list):
        input_dict = {
            "messages": messages
        }
        emitted_texts = set()

        for chunk in self.agent.stream(input_dict, stream_mode="values", context={"report": False}): # 此时的chunk是一个字典
              latest_message = chunk["messages"][-1]
              visible_text = self._extract_user_visible_text(latest_message)
              if visible_text and visible_text not in emitted_texts:
                  emitted_texts.add(visible_text)
                  yield visible_text


if __name__ == '__main__':
    agent = ReactAgent()

    test_messages = [{"role": "user", "content": "扫地机器人在我的城市及天气下该如何保养"}]
    for chunk1 in agent.execute_stream(test_messages):  # 此时的chunk1是一个字符串
        print(chunk1, end="", flush=True)
