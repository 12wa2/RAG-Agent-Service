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


def _clean_city_name(city: str | None) -> str:
    if not city:
        return ""
    return city.strip()


def resolve_city_from_coordinates(longitude: float | None, latitude: float | None) -> str:
    """优先使用前端提供的经纬度，通过高德逆地理编码解析城市。"""
    if longitude is None or latitude is None:
        return ""

    url = "https://restapi.amap.com/v3/geocode/regeo"
    params = {
        "location": f"{longitude},{latitude}",
        "key": agent_conf["AMAP_KEY"],
        "extensions": "base",
    }

    try:
        data = requests.get(url, params=params, timeout=5).json()
        logger.info(f"【高德逆地理编码Debug】返回的数据是：{data}")

        if data.get("status") != "1":
            logger.warning(f"[定位警告] 高德逆地理编码失败: {data}")
            return ""

        address_component = data.get("regeocode", {}).get("addressComponent", {})
        city = address_component.get("city")
        province = address_component.get("province")

        if isinstance(city, list):
            city = city[0] if city else ""

        if isinstance(city, str) and city.strip():
            return city.strip()

        if isinstance(province, str) and province.strip():
            return province.strip()

        return ""
    except Exception as e:
        logger.error(f"[定位警告] 高德逆地理编码调用失败: {e}")
        return ""


def resolve_city_from_ip(client_ip: str | None = None) -> str:
    """使用高德IP定位城市，可传入真实客户端IP，不传则退化为服务端出口IP。"""
    url = "https://restapi.amap.com/v3/ip"
    params = {"key": agent_conf["AMAP_KEY"]}
    if client_ip:
        params["ip"] = client_ip

    try:
        data = requests.get(url, params=params, timeout=5).json()
        logger.info(f"【高德IP定位Debug】返回的数据是：{data}")

        if data.get("status") == "1" and data.get("city"):
            city = data["city"]
            if isinstance(city, str) and city.strip():
                return city.strip()

        logger.warning(f"[定位警告] 高德IP定位未返回有效城市: {data}")
        return ""
    except Exception as e:
        logger.error(f"[定位警告] 高德IP定位调用失败: {e}")
        return ""


def resolve_city_from_inputs(
    city: str | None = None,
    longitude: float | None = None,
    latitude: float | None = None,
    client_ip: str | None = None,
) -> tuple[str, str]:
    """按优先级解析城市：用户输入 > 前端经纬度 > 客户端IP > 服务端IP。"""
    cleaned_city = _clean_city_name(city)
    if cleaned_city:
        return cleaned_city, "user_provided_city"

    geo_city = resolve_city_from_coordinates(longitude=longitude, latitude=latitude)
    if geo_city:
        return geo_city, "frontend_coordinates"

    ip_city = resolve_city_from_ip(client_ip=client_ip)
    if ip_city:
        return ip_city, "client_ip" if client_ip else "server_ip"

    return "", ""



@tool(description="根据用户问题，从知识库中检索相关文档并进行的总结")
def rag_summarize(query:str)->str:
    return rag.rag_summarize(query)

@tool(description="获取指定城市的实时天气信息。仅当已经明确知道城市名称时调用，若用户已在问题中提供城市名称，应直接使用该城市。")
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
        logger.error(f"[天气API异常] {e}")
        return f"当前网络异常，无法获取{city_name}的天气。"



@tool(description="兜底定位工具：在用户未提供城市、前端也未提供有效定位结果时，使用高德IP定位粗略获取城市名称。若已有更高优先级的位置结果，禁止调用本工具覆盖。")
def get_user_loction() -> str:
    """调用高德API，使用当前服务端出口IP进行兜底定位。"""
    return resolve_city_from_ip()


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

