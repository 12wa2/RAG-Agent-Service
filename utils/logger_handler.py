"""日志工具"""
import logging
from utils.path_tool import get_abs_path
import os
from datetime import datetime

# 日志保存的根目录
LOG_ROOT = get_abs_path('logs')

# 确保日志的目录存在
os.makedirs(LOG_ROOT, exist_ok=True)

#日志的格式配置
DEFAULT_LOG_FORMAT = logging.Formatter ( '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')


def get_logger(
        name: str = "agent",  # 日志管理器的名字，默认为 "agent"
        console_level: int = logging.INFO,  # 屏幕（控制台）显示的最低级别，默认只看重要信息
        file_level: int = logging.DEBUG,  # 文件记录的最低级别，默认记录所有细节
        log_file=None,  # 指定日志文件名，如果不传则自动生成
) -> logging.Logger:  # 声明函数返回的是一个 logging.Logger 对象
    # 1. 获取（或创建）一个叫 name 的日志管理器
    logger = logging.getLogger(name)

    # 2. 设置日志管理器的“总闸门”级别为 DEBUG（确保所有级别的信号都能流进这个日志管理器）
    logger.setLevel(logging.DEBUG)

    # 3. 关键防御：检查这个日志器是否已经装过“处理器”了。
    # 如果已经装过了（logger.handlers 不为空），直接返回，防止重复打印
    if logger.handlers:
        return logger

    # --- 配置控制台通路 (Console Handler) ---
    # 4. 创建一个把日志发往屏幕的处理器
    console_handler = logging.StreamHandler()
    # 5. 设置屏幕显示的级别（比如只显示 INFO 及以上）
    console_handler.setLevel(console_level)
    # 6. 给屏幕显示的日志穿上“统一制服”（设置格式）
    console_handler.setFormatter(DEFAULT_LOG_FORMAT)
    # 7. 把这个屏幕处理器安装到日志器上
    logger.addHandler(console_handler)

    # --- 配置输出文件通路 (File Handler) ---
    # 8. 如果用户没指定文件名，就根据当前日期生成一个（如：agent_20260424.log），也就是日志文件的绝对路径
    if not log_file:
        log_file = os.path.join(LOG_ROOT, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")

    # 9. 创建一个把日志写入文件的处理器，并指定编码为 utf-8（防止中文乱码）
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    # 10. 设置文件记录的级别（通常设为 DEBUG，记录所有蛛丝马迹）
    file_handler.setLevel(file_level)
    # 11. 给文件里的日志也穿上“统一制服”
    file_handler.setFormatter(DEFAULT_LOG_FORMAT)
    # 12. 把这个文件处理器也安装到日志器上
    logger.addHandler(file_handler)

    # 13. 大功告成，返回配置好的日志管理器，此时日志处理器中有屏幕处理器和文件处理器
    return logger


# 快捷获取日志器：直接调用函数，获取默认配置的 logger
logger = get_logger()

if __name__ == '__main__':
    logger.info("信息日志")
    logger.error("错误日志")
    logger.warning("警告日志")
    logger.debug("调试日志")
