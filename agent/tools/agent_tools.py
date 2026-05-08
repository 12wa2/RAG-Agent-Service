from langchain.tools import tool
import os
import random
from rag.rag_service import RagSummarizeService
from utils.path_tool import get_abs_path
from utils.config_handler import agent_conf
from utils.logger_handler import logger
import requests

rag=RagSummarizeService()

user_ids = ["1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008", "1009", "1010",]
month_arr = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06",
             "2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12", ]

external_data = {}



@tool(description="根据用户问题，从知识库中检索相关文档并进行的总结")
def rag_summarize(query:str)->str:
    return rag.rag_summarize(query)


@tool(description="获取用户所在的城市天气,以消息字符串形式返回")
def get_user_weather(city: str) -> str:
    """调用高德API，根据城市名称获取实时天气"""
    # 简单的清洗，防止传入空值
    if not city:
        return "请提供具体的城市名称。"
        
    city_name = city.strip()

    try:
        # ==========================================
        # 第一步：把“城市名”转换成高德能懂的“adcode”
        # ==========================================
        district_url = f"https://restapi.amap.com/v3/config/district?keywords={city_name}&key={agent_conf['AMAP_KEY']}"
        dist_res = requests.get(district_url, timeout=5).json()
        
        # 容错：如果没有查到这个城市
        if dist_res.get("status") != "1" or not dist_res.get("districts"):
            return f"抱歉，未能识别城市：{city_name}"
            
        adcode = dist_res["districts"][0]["adcode"]

        # ==========================================
        # 第二步：拿 adcode 去查真正的实时天气
        # ==========================================
        weather_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={adcode}&key={agent_conf['AMAP_KEY']}&extensions=base"
        weather_res = requests.get(weather_url, timeout=5).json()
        
        # 解析天气数据并拼接成人类可读的字符串
        if weather_res.get("status") == "1" and weather_res.get("lives"):
            live = weather_res["lives"][0]
            
            # 返回一段格式化的纯文本，Agent 看到这段话就能理解天气了
            return (f"城市【{live['city']}】当前天气为{live['weather']}，"
                    f"气温{live['temperature']}摄氏度，"
                    f"空气湿度{live['humidity']}%，"
                    f"{live['winddirection']}风{live['windpower']}级，"
                    f"数据发布时间：{live['reporttime']}")
                    
        return f"抱歉，暂时无法获取{city_name}的天气数据。"

    except Exception as e:
        # 防御性编程：断网或接口超时，不能让整个 Agent 崩溃
        print(f"[天气API异常] {e}")
        return f"当前网络异常，无法获取{city_name}的天气。"



@tool(description="获取用户所在的城市名称,以字符串形式返回")
def get_user_loction() -> str:
    """调用高德API，根据当前网络的IP自动获取所在城市"""
    url = f"https://restapi.amap.com/v3/ip?key={agent_conf['AMAP_KEY']}"
    
    try:
        response = requests.get(url, timeout=5) # 加个5秒超时，防止一直卡住
        data = response.json()
        

        # 🌟 加上这行排查代码！看看终端里打印出了什么秘密！
        print(f"【高德定位Debug】返回的数据是：{data}")

        # status 为 1 表示高德接口请求成功
        if data.get('status') == '1' and data.get('city'):
            # 高德返回的可能是空数组 []（如果IP查不到），所以要做个判断
            if isinstance(data['city'], str): 
                return data['city']
                
        # 如果定位失败（比如查不到），给 Agent 兜底返回一个默认城市，防止程序崩溃
        return "深圳市" 
        
    except Exception as e:
        # 万一断网了，也返回默认城市
        print(f"[定位警告] 高德API调用失败: {e}")
        return "深圳市"


@tool(description="获取用户的ID，以字符串形式返回")
def get_user_id()->str:
    return random.choice(user_ids)

@tool(description="获取当前月份，以字符串形式返回")
def get_current_month()->str:
    return random.choice(month_arr)


def generate_external_data():
    """
     {
         "user_id": {
             "month" : {"特征": xxx, "效率": xxx, ...}
             "month" : {"特征": xxx, "效率": xxx, ...}
             "month" : {"特征": xxx, "效率": xxx, ...}
             ...
         },
         "user_id": {
             "month" : {"特征": xxx, "效率": xxx, ...}
             "month" : {"特征": xxx, "效率": xxx, ...}
             "month" : {"特征": xxx, "效率": xxx, ...}
             ...
         },
         "user_id": {
             "month" : {"特征": xxx, "效率": xxx, ...}
             "month" : {"特征": xxx, "效率": xxx, ...}
             "month" : {"特征": xxx, "效率": xxx, ...}
             ...
         },
         ...
     }
     :return:
     """
    if not external_data:  # 为了防止多次加载外部数据
        external_data_path = get_abs_path(agent_conf["external_data_path"])

        if not os.path.exists(external_data_path):
            raise FileNotFoundError(f"外部数据文件不存在: {external_data_path}")

        with open(external_data_path, "r", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                arr: list[str] = line.strip().split(",")

                user_id:str = arr[0].replace('"', "")
                feature:str = arr[1].replace('"', "")
                efficiency:str = arr[2].replace('"', "")
                consumption:str = arr[3].replace('"', "")
                comparison:str = arr[4].replace('"', "")
                time:str = arr[5].replace('"', "")

                if user_id not in external_data:
                    external_data[user_id] = {}

                external_data[user_id][time] = {
                    "特征": feature,
                    "效率": efficiency,
                    "消耗": consumption,
                    "比较": comparison,
                    "时间": time
                }


@tool(description="从外部系统中获取指定用户在指定月份的使用记录，以纯字符串形式返回，如未检索到返回空字符串")
def fetch_external_data(user_id:str, month:str)->str:
    generate_external_data()

    try:
       return external_data[user_id][month]
    except KeyError:
        logger.warning(f"[fetch_external_data]未能检索到用户：{user_id}在{month}的使用记录数据")
        return ""


@tool(description="无入参，无返回值，调用后触发中间件自动为报告生成的场景动态注入上下文信息，为后续提示词切换提供上下文信息")
def fill_context_for_report()->bool:  # 用来触发中间件自动为报告生成的场景动态注入上下文信息，就是只要调用这个工具，在middleware.py中会有把report键设为True的操作
    return "fill_context_for_report已调用"

