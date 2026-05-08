import pymysql
from utils.logger_handler import logger
from utils.config_handler import agent_conf

# ==========================================
# 1. 数据库配置读取
# ==========================================
# 尝试从配置文件 (agent.yml) 中读取 mysql_config 节点
# 如果配置文件里没写，就使用后面的默认字典作为“兜底”配置
db_config = agent_conf["mysql_config"]

def get_connection(use_db=True):
    """获取 MySQL 数据库连接"""
    try:
        # 使用 pymysql 建立与数据库的连接
        conn = pymysql.connect(
            host=db_config["host"],
            port=db_config["port"],
            user=db_config["user"],
            password=db_config["password"],
            # 如果 use_db=True，连接时直接进入指定的数据库（agent_memory）
            # 如果 use_db=False，只连接到 MySQL 服务器（通常用于第一次建库时）
            database=db_config["database"] if use_db else None,
            charset='utf8mb4', # 必须用 utf8mb4，否则无法存储 Emoji 等特殊字符
            # 关键设置：让查出来的结果变成字典格式（如 {'id':1, 'role':'user'}），而不是默认的元组 (1, 'user')
            cursorclass=pymysql.cursors.DictCursor 
        )
        return conn
    except Exception as e:
        logger.error(f"MySQL 连接失败: {e}")
        raise e

def init_db():
    """初始化数据库和表结构（程序启动时自动检查，没有就建）"""
    # ----------------------------------
    # 步骤 A：确保数据库存在
    # ----------------------------------
    try:
        # 此时连的是 MySQL 服务器，还没进具体的库
        conn = get_connection(use_db=False)
        cursor = conn.cursor()
        # 执行 SQL：如果库不存在，就创建一个。并指定字符集支持各种语言和表情
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_config['database']} DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit() # 提交让修改生效
        conn.close()  # 用完立刻关闭连接，释放资源
    except Exception as e:
        logger.error(f"创建数据库失败: {e}")
        return

    # ----------------------------------
    # 步骤 B：进入具体的库，确保两张表存在
    # ----------------------------------
    try:
        # 此时连入我们刚刚创建的 agent_memory 库
        conn = get_connection(use_db=True)
        cursor = conn.cursor()
        
        # 1. 创建【会话表 sessions】：用来存左侧边栏的对话列表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id VARCHAR(255) PRIMARY KEY, -- 对话的唯一ID，作为主键
                title VARCHAR(255) NOT NULL,         -- 对话的标题
                summary LONGTEXT DEFAULT NULL,       -- [新增] 存储该会话的长记忆摘要
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 自动记录创建时间
            ) ENGINE=InnoDB
        ''')
        
        # 为了兼容已经建过表的情况，我们尝试给老表增加 summary 字段
        try:
            cursor.execute("ALTER TABLE sessions ADD COLUMN summary LONGTEXT DEFAULT NULL")
        except Exception:
            pass # 如果字段已存在，就会报错抛异常，我们忽略即可
        
        # 2. 创建【消息表 messages】：用来存右侧聊天框里的一句句话
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INT PRIMARY KEY AUTO_INCREMENT,   -- 每句话一个自增序号
                session_id VARCHAR(255) NOT NULL,    -- 这句话属于哪个对话（关联会话表）
                role VARCHAR(50) NOT NULL,           -- 谁说的（user 还是 assistant）
                content LONGTEXT NOT NULL,           -- 说了什么内容（用LONGTEXT支持超长文本）
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                -- 关键约束：外键。意味着如果我们在会话表删除了某个 session_id，
                -- 这张表里对应的所有消息也会被自动“级联删除 (ON DELETE CASCADE)”
                FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"初始化数据库表失败: {e}")

def load_history_from_db():
    """从 MySQL 数据库中加载所有会话及历史消息，拼成 Streamlit 需要的字典格式"""
    init_db() # 每次加载前，先确保表没丢
    history = {} # 准备一个空字典装数据
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 1. 把左侧边栏需要的“所有会话”查出来，连同摘要一起捞出
        cursor.execute("SELECT session_id, title, summary FROM sessions ORDER BY created_at ASC")
        sessions = cursor.fetchall()
        
        # 2. 遍历每一个会话
        for row in sessions:
            session_id = row['session_id']
            # 在字典里搭框架：增加 summary 字段
            history[session_id] = {"title": row['title'], "summary": row.get('summary') or "", "messages": []}
            
            # 3. 针对当前遍历到的这一个会话，去消息表里把它所有的聊天记录按时间顺序捞出来
            cursor.execute("SELECT role, content FROM messages WHERE session_id = %s ORDER BY id ASC", (session_id,))
            msgs = cursor.fetchall()
            
            # 4. 把捞出来的聊天记录一条条塞进刚才搭好的框架的 messages 列表里
            for msg_row in msgs:
                history[session_id]["messages"].append({"role": msg_row['role'], "content": msg_row['content']})
                
        conn.close()
    except Exception as e:
        logger.error(f"加载数据库历史记录失败: {e}")
        
    # 最后返回拼装好的大字典，直接喂给 st.session_state["chat_history"]
    return history

def save_history_to_db(history_dict):
    """把 Streamlit 内存里的最新字典数据，全部同步到 MySQL 里"""
    init_db()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # ----------------------------------
        # 阶段 A：清理已经删掉的会话
        # ----------------------------------
        # 1. 查出数据库里现在存了哪些 session_id
        cursor.execute("SELECT session_id FROM sessions")
        existing_sessions = {row['session_id'] for row in cursor.fetchall()}
        # 2. 拿到前端内存里现在有哪些 session_id
        current_sessions = set(history_dict.keys())
        
        # 3. 如果数据库里有的 ID，前端内存里没有了（说明用户在网页上点“删除当前”了）
        for s_id in existing_sessions - current_sessions:
            # 就在数据库里把这个会话删掉。
            # (因为建表时写了 ON DELETE CASCADE，所以对应的 messages 也会自动消失)
            cursor.execute("DELETE FROM sessions WHERE session_id = %s", (s_id,))
            
        # ----------------------------------
        # 阶段 B：保存/更新当前还在的会话和消息
        # ----------------------------------
        for session_id, data in history_dict.items():
            title = data["title"]
            summary = data.get("summary", "")
            
            # 1. 处理 sessions 表
            if session_id not in existing_sessions:
                # 这是一个全新的会话，插入新数据
                cursor.execute("INSERT INTO sessions (session_id, title, summary) VALUES (%s, %s, %s)", (session_id, title, summary))
            else:
                # 这个会话已经存在了，有可能标题或摘要被改了，执行更新操作
                cursor.execute("UPDATE sessions SET title = %s, summary = %s WHERE session_id = %s", (title, summary, session_id))
                
            # 2. 处理 messages 表 (采用暴力但简单有效的全量替换法)
            # 先无脑把当前会话在数据库里的所有旧消息全删了
            cursor.execute("DELETE FROM messages WHERE session_id = %s", (session_id,))
            
            # 再把前端内存里的消息列表从头到尾重新插入一遍
            for msg in data["messages"]:
                cursor.execute("INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)", 
                               (session_id, msg["role"], msg["content"]))
                               
        # 提交所有修改并关闭连接
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"保存数据库历史记录失败: {e}")

# 给函数起个别名，方便外部直接调用 load_history() 和 save_history()
load_history = load_history_from_db
save_history = save_history_to_db