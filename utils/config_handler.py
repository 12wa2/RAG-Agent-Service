"""
配置文件处理
"""
"""
yaml
k:v
"""
import yaml  # 导入解析库，它是 Python 处理 YAML 文件的标准工具
from utils.path_tool import get_abs_path  # 导入自定义工具，将相对路径转为绝对路径，防止找不到文件


def load_rag_config(
    # 参数1: config_path，默认指向项目根目录下 config 文件夹里的 rag.yml
    config_path: str = get_abs_path('config/rag.yml'),
    # 参数2: encoding，默认使用 utf-8，确保能正确读取配置文件里的中文
    encoding: str = 'utf-8'
):
    """
    该函数的作用是：读取指定的 YAML 配置文件，并将其转换为 Python 字典
    """
    # 使用 with 语句打开文件（上下文管理器），优点是：文件读完后会自动关闭，释放系统资源
    with open(config_path, 'r', encoding=encoding) as f:
        # yaml.load 是核心动作，将文件流 f 转换为字典
        # Loader=yaml.FullLoader 是一种更安全、更完整的加载模式，官方目前推荐使用它
        return yaml.load(f, Loader=yaml.FullLoader)

# --- 全局初始化 ---
# 在模块加载时就运行一次函数，把配置结果存入变量 rag_conf
# 这样其他脚本只需要 from this_file import rag_conf 就能直接用了
rag_conf = load_rag_config()    # 此时 rag_conf就是可以当字典来用的


def load_chroma_config(config_path: str=get_abs_path('config/chroma.yml'),encoding: str='utf-8'):
    with open(config_path, 'r', encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_prompts_config(config_path: str=get_abs_path('config/prompts.yml'),encoding: str='utf-8'):
    with open(config_path, 'r', encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_agent_config(config_path: str=get_abs_path('config/agent.yml'),encoding: str='utf-8'):
    with open(config_path, 'r', encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)


chroma_conf = load_chroma_config()
prompts_conf = load_prompts_config()
agent_conf = load_agent_config()


# --- 测试模块 ---
# 只有当你直接运行这个 py 文件时，下面的代码才会执行
# 如果这个文件被别人 import 调用，下面这块代码会被忽略
if __name__ == '__main__':
    # 尝试打印配置文件中键名为 "chat_model_name" 的值
    # 如果 rag.yaml 里写了 chat_model_name: "qwen-max"，这里就会输出 qwen-max
    print(rag_conf["chat_model_name"])

