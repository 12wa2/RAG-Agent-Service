from model.factory import chat_model
from langchain.agents import create_agent
from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import (rag_summarize, get_user_weather, get_user_loction, get_user_id,
                                     get_current_month, fetch_external_data, fill_context_for_report)
from agent.tools.middleware import monitor_tool, log_before_model, report_prompt_switch

class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model = chat_model,
            system_prompt = load_system_prompts(),
            tools = [rag_summarize, get_user_weather, get_user_loction, get_user_id,
                     get_current_month, fetch_external_data, fill_context_for_report],
            middleware = [monitor_tool, log_before_model, report_prompt_switch],
        )

    def execute_stream(self, messages: list):
        input_dict = {
            "messages": messages
        }

        for chunnk in  self.agent.stream(input_dict,stream_mode="values",context={"report": False}): # 此时的chunnk是一个字典
              latest_message = chunnk["messages"][-1]
              if latest_message.content:
                  yield latest_message.content.strip()+"\n"


if __name__ == '__main__':
    agent = ReactAgent()

    test_messages = [{"role": "user", "content": "扫地机器人在我的城市及天气下该如何保养"}]
    for chunk1 in agent.execute_stream(test_messages):  # 此时的chunk1是一个字符串
        print(chunk1, end="", flush=True)
