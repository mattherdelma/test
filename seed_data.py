"""生成演示数据：默认 3 年共约 1500 条事故记录"""
import random
from datetime import datetime, timedelta
from database import init_db, get_db, DEFAULT_DICTS

# 东海县真实道路（城区主次干道 + 过境国省道 + 高速）
ROADS = [
    ('牛山路', '城市主干道'), ('晶都大道', '城市主干道'), ('富华路', '城市主干道'),
    ('振兴路', '城市主干道'), ('和平路', '城市主干道'), ('利民路', '城市主干道'),
    ('海陵路', '城市主干道'), ('东海大道', '城市主干道'), ('人民路', '城市主干道'),
    ('青年路', '城市次干道'), ('幸福路', '城市次干道'), ('郑庄路', '城市次干道'),
    ('黄海路', '城市次干道'), ('学院路', '城市次干道'), ('安峰路', '城市次干道'),
    ('G310国道', '国道'), ('S324省道', '省道'), ('S236省道', '省道'),
    ('S270省道', '省道'), ('S326省道', '省道'),
    ('G2京沪高速', '高速公路'), ('G30连霍高速', '高速公路'), ('G1516盐洛高速', '高速公路'),
]
SURNAMES = '赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜'
GIVEN = '伟芳娜敏静秀丽强磊军洋勇艳杰娟涛明超秀兰霞平刚桂英文华建国春梅志强建华丽华志伟玉兰桂兰玉梅秀珍'


def rand_name():
    return random.choice(SURNAMES) + ''.join(random.sample(GIVEN, random.randint(1, 2)))


def rand_plate():
    # 连云港车牌为「苏G」，演示数据以本地车牌为主，少量外地车
    if random.random() < 0.8:
        prefix = '苏G'
    else:
        prefix = random.choice(['苏A', '苏B', '苏C', '鲁Q', '鲁L', '皖N', '京A'])
    return prefix + ''.join(random.choices('0123456789ABCDEFGHJKLMNPQRSTUVWXYZ', k=5))


def rand_id_card():
    # 东海县行政区划代码 320722
    base = '320722' + str(random.randint(1960, 2002)) + str(random.randint(1, 12)).zfill(2) + str(random.randint(1, 28)).zfill(2)
    return base + ''.join(random.choices('0123456789', k=3)) + random.choice('0123456789X')


def seed(n_per_year=500, years=3):
    init_db()
    with get_db() as conn:
        cur = conn.execute('SELECT COUNT(*) AS c FROM accidents')
        if cur.fetchone()['c'] > 0:
            print('已有数据，跳过生成。如需重置请删除 data/accidents.db')
            return

        today = datetime.now()
        seq = 1
        total = 0
        for year_offset in range(years):
            year = today.year - year_offset
            for _ in range(n_per_year):
                # 时间分布：早晚高峰、夜间多发
                hour_weights = [3, 2, 2, 1, 1, 2, 4, 8, 10, 7, 5, 5, 6, 5, 5, 6, 7, 9, 8, 6, 5, 4, 4, 3]
                hour = random.choices(range(24), weights=hour_weights)[0]
                month = random.randint(1, 12)
                if year == today.year and month > today.month:
                    continue
                day = random.randint(1, 28)
                occur_time = datetime(year, month, day, hour, random.randint(0, 59))
                if occur_time > today:
                    continue
                report_time = occur_time + timedelta(minutes=random.randint(5, 60))

                # 事故等级：轻微最多
                level = random.choices(
                    DEFAULT_DICTS['level'],
                    weights=[60, 30, 8, 2]
                )[0]
                death = 0
                injury = 0
                loss = 0
                if level == '轻微事故':
                    injury = random.choices([0, 1], weights=[7, 3])[0]
                    loss = random.randint(500, 5000)
                elif level == '一般事故':
                    injury = random.randint(1, 3)
                    loss = random.randint(3000, 30000)
                elif level == '重大事故':
                    death = random.randint(1, 2)
                    injury = random.randint(2, 8)
                    loss = random.randint(30000, 300000)
                else:
                    death = random.randint(3, 6)
                    injury = random.randint(5, 20)
                    loss = random.randint(300000, 2000000)

                road = random.choice(ROADS)
                acc_no = f'JT{occur_time.strftime("%Y%m%d")}{seq:04d}'
                seq += 1
                # 演示数据经纬度：落在东海县范围内 (经度 118.45-119.0, 纬度 34.35-34.85)
                # 约 55% 聚集在县城（牛山/晶都/石榴街道）一带，其余散布各乡镇
                if random.random() < 0.55:
                    lon = round(118.72 + random.uniform(-0.06, 0.08), 6)
                    lat = round(34.54 + random.uniform(-0.05, 0.06), 6)
                else:
                    lon = round(118.45 + random.random() * 0.55, 6)
                    lat = round(34.35 + random.random() * 0.50, 6)

                cur = conn.execute('''
                    INSERT INTO accidents(
                        accident_no, occur_time, report_time, level, type,
                        weather, visibility, district, road_name, road_section,
                        mileage, longitude, latitude, road_type, road_shape, road_condition,
                        death_count, injury_count, economic_loss,
                        cause, handle_result, handler, remarks, created_by
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (
                    acc_no,
                    occur_time.strftime('%Y-%m-%d %H:%M'),
                    report_time.strftime('%Y-%m-%d %H:%M'),
                    level,
                    random.choice(DEFAULT_DICTS['type']),
                    random.choices(DEFAULT_DICTS['weather'], weights=[50, 20, 15, 5, 7, 3])[0],
                    random.choices(DEFAULT_DICTS['visibility'], weights=[60, 25, 10, 5])[0],
                    random.choice(DEFAULT_DICTS['district']),
                    road[0],
                    f'{random.randint(1, 30)}号段',
                    f'K{random.randint(1, 200)}+{random.randint(0, 900)}',
                    lon, lat,
                    road[1],
                    random.choice(DEFAULT_DICTS['road_shape']),
                    random.choices(DEFAULT_DICTS['road_condition'], weights=[55, 20, 10, 5, 5, 5])[0],
                    death, injury, loss,
                    random.choice(DEFAULT_DICTS['cause']),
                    random.choice(['已结案', '调解中', '诉讼中', '已撤案']),
                    rand_name(),
                    '',
                    2
                ))
                acc_id = cur.lastrowid

                for _ in range(random.randint(1, 3)):
                    conn.execute('''
                        INSERT INTO vehicles(accident_id, plate_no, vehicle_type, owner, insurance, use_type)
                        VALUES (?,?,?,?,?,?)
                    ''', (
                        acc_id, rand_plate(),
                        random.choice(DEFAULT_DICTS['vehicle_type']),
                        rand_name(),
                        random.choice(['平安', '人保', '太平洋', '阳光', '中华联合', '未投保']),
                        random.choice(DEFAULT_DICTS['use_type'])
                    ))

                for i in range(random.randint(1, 4)):
                    is_drunk = 1 if random.random() < 0.05 else 0
                    if injury > 0 and i == 0:
                        inj = random.choice(['轻伤', '重伤'])
                    elif death > 0 and i == 0:
                        inj = '死亡'
                    else:
                        inj = '无伤'
                    conn.execute('''
                        INSERT INTO persons(accident_id, name, id_card, gender, age, driving_years, drunk, responsibility, injury_level)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    ''', (
                        acc_id, rand_name(), rand_id_card(),
                        random.choice(['男', '女']),
                        random.randint(20, 65),
                        random.randint(0, 30),
                        is_drunk,
                        random.choices(DEFAULT_DICTS['responsibility'], weights=[10, 35, 20, 25, 10])[0],
                        inj
                    ))
                total += 1
        print(f'已生成 {total} 条演示事故记录')


if __name__ == '__main__':
    seed()
