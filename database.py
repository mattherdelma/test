import os
import sys
import sqlite3
from contextlib import contextmanager
from werkzeug.security import generate_password_hash

# 数据目录：打包后放在 exe 旁；开发时放在项目下
if getattr(sys, 'frozen', False):
    _APP_BASE = os.path.dirname(sys.executable)
else:
    _APP_BASE = os.path.dirname(os.path.abspath(__file__))

DB_DIR = os.path.join(_APP_BASE, 'data')
DB_PATH = os.path.join(DB_DIR, 'accidents.db')

# 适用区域：江苏省连云港市东海县（行政区划代码 320722）
REGION_NAME = '连云港市东海县'
REGION_CODE = '320722'
# 东海县地理中心（牛山街道附近），用于地图默认定位
REGION_CENTER = [118.752, 34.542]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'recorder',
    name TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS accidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accident_no TEXT UNIQUE NOT NULL,
    occur_time TEXT NOT NULL,
    report_time TEXT,
    level TEXT,
    type TEXT,
    weather TEXT,
    visibility TEXT,
    district TEXT,
    road_name TEXT,
    road_section TEXT,
    mileage TEXT,
    longitude REAL,
    latitude REAL,
    road_type TEXT,
    road_shape TEXT,
    road_condition TEXT,
    death_count INTEGER DEFAULT 0,
    injury_count INTEGER DEFAULT 0,
    economic_loss REAL DEFAULT 0,
    cause TEXT,
    handle_result TEXT,
    handler TEXT,
    remarks TEXT,
    photos TEXT,
    created_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_acc_time ON accidents(occur_time);
CREATE INDEX IF NOT EXISTS idx_acc_district ON accidents(district);
CREATE INDEX IF NOT EXISTS idx_acc_level ON accidents(level);
CREATE INDEX IF NOT EXISTS idx_acc_type ON accidents(type);
CREATE INDEX IF NOT EXISTS idx_acc_road ON accidents(road_name);

CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accident_id INTEGER NOT NULL,
    plate_no TEXT,
    vehicle_type TEXT,
    owner TEXT,
    insurance TEXT,
    use_type TEXT,
    FOREIGN KEY (accident_id) REFERENCES accidents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_veh_acc ON vehicles(accident_id);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accident_id INTEGER NOT NULL,
    name TEXT,
    id_card TEXT,
    gender TEXT,
    age INTEGER,
    driving_years INTEGER,
    drunk INTEGER DEFAULT 0,
    responsibility TEXT,
    injury_level TEXT,
    FOREIGN KEY (accident_id) REFERENCES accidents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_per_acc ON persons(accident_id);

CREATE TABLE IF NOT EXISTS dictionaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    UNIQUE(category, name)
);
CREATE INDEX IF NOT EXISTS idx_dict_cat ON dictionaries(category);

CREATE TABLE IF NOT EXISTS operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    action TEXT,
    target TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
"""

DEFAULT_DICTS = {
    'level': ['轻微事故', '一般事故', '重大事故', '特大事故'],
    'type': ['追尾', '正面碰撞', '侧面碰撞', '刮擦', '翻车', '碾压', '撞固定物', '其他'],
    'weather': ['晴', '阴', '雨', '雪', '雾', '大风'],
    'visibility': ['良好', '一般', '较差', '极差'],
    'road_type': ['高速公路', '国道', '省道', '县道', '乡道', '城市主干道', '城市次干道', '小区道路'],
    'road_shape': ['平直', '弯道', '坡道', '弯坡组合', '桥梁', '隧道', '交叉路口'],
    'road_condition': ['干燥', '潮湿', '积水', '积雪', '结冰', '泥泞'],
    'vehicle_type': ['小型轿车', 'SUV', '面包车', '中型客车', '大型客车', '轻型货车', '重型货车', '摩托车', '电动自行车', '自行车', '其他'],
    'use_type': ['私家车', '公务车', '营运客车', '营运货车', '出租车', '校车', '危化品运输', '其他'],
    'cause': ['超速行驶', '酒后驾驶', '疲劳驾驶', '违章变道', '违章超车', '违章掉头', '违反信号灯', '未保持安全距离', '操作不当', '行人违章', '机械故障', '其他'],
    'responsibility': ['全部', '主要', '同等', '次要', '无'],
    'injury_level': ['无伤', '轻伤', '重伤', '死亡'],
    # 东海县实际下辖街道/乡镇（共 2 个街道、14 个镇、4 个乡，可在「字典维护」中增删）
    'district': [
        '牛山街道', '石榴街道',
        '白塔埠镇', '房山镇', '平明镇', '桃林镇', '洪庄镇', '双店镇',
        '青湖镇', '温泉镇', '黄川镇', '石梁河镇', '安峰镇', '曲阳镇',
        '山左口镇', '驼峰乡', '李埝乡', '张湾乡', '横沟乡', '海陵路街道',
    ],
}


@contextmanager
def get_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    with get_db() as conn:
        conn.executescript(SCHEMA)
        cur = conn.execute('SELECT COUNT(*) AS c FROM users')
        if cur.fetchone()['c'] == 0:
            conn.execute(
                'INSERT INTO users(username,password_hash,role,name) VALUES (?,?,?,?)',
                ('admin', generate_password_hash('admin123'), 'admin', '系统管理员')
            )
            conn.execute(
                'INSERT INTO users(username,password_hash,role,name) VALUES (?,?,?,?)',
                ('recorder', generate_password_hash('123456'), 'recorder', '录入员')
            )
            conn.execute(
                'INSERT INTO users(username,password_hash,role,name) VALUES (?,?,?,?)',
                ('viewer', generate_password_hash('123456'), 'viewer', '查看者')
            )
        cur = conn.execute('SELECT COUNT(*) AS c FROM dictionaries')
        if cur.fetchone()['c'] == 0:
            for category, items in DEFAULT_DICTS.items():
                for i, name in enumerate(items):
                    conn.execute(
                        'INSERT OR IGNORE INTO dictionaries(category,name,sort_order) VALUES (?,?,?)',
                        (category, name, i)
                    )


def get_dict_options(category):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT name FROM dictionaries WHERE category=? ORDER BY sort_order,id',
            (category,)
        ).fetchall()
        return [r['name'] for r in rows]


def get_all_dicts():
    result = {}
    with get_db() as conn:
        rows = conn.execute(
            'SELECT category,name FROM dictionaries ORDER BY category,sort_order,id'
        ).fetchall()
        for r in rows:
            result.setdefault(r['category'], []).append(r['name'])
    return result


def log_action(user_id, username, action, target=''):
    try:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO operation_logs(user_id,username,action,target) VALUES (?,?,?,?)',
                (user_id, username, action, target)
            )
    except Exception:
        pass


if __name__ == '__main__':
    init_db()
    print(f'数据库已初始化: {DB_PATH}')
