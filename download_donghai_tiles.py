"""
下载东海县离线地图瓦片，实现「高德式」可缩放、逐层看街道细节的离线底图。

在【能联网】的机器上运行一次（之后把生成的 tiles/ 目录连同程序一起拷到离线机）：

    python download_donghai_tiles.py

策略（街道级，约 9 千张瓦片 / 200~300MB）：
  · 全县范围      z10–z15   能看到县域、乡镇、主次干道到街道
  · 县城核心区    z16–z18   牛山/石榴街道一带，能看到小巷、门牌级细节

瓦片保存为   tiles/{z}/{x}/{y}.png   ，程序通过 /tiles/{z}/{x}/{y}.png 离线读取。
脚本可断点续传（已存在的瓦片自动跳过），中断后重跑即可继续。

关于瓦片来源与合规：
  · 默认使用 OpenStreetMap 标准瓦片（ODbL，署名即可）。OSM 对大批量下载有使用约束，
    本脚本仅下载东海县这一小范围、限定层级，并加了请求间隔以示礼貌。
  · 如贵单位有自建/授权的瓦片服务，把 TILE_URL 改成对应模板即可（如天地图离线包、
    自建 OSM 瓦片服务等），其余逻辑不变。
"""
import os
import ssl
import math
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
TILES_DIR = os.path.join(BASE, 'tiles')

# 瓦片源模板：{z}/{x}/{y}。如有自建/授权瓦片服务，改这里即可。
# 备用公共源（轮询）：
TILE_URLS = [
    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
    'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
    'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png',
]

# 下载范围（西, 南, 东, 北）
COUNTY_BBOX = (118.40, 34.30, 119.08, 34.95)   # 东海县全域
URBAN_BBOX = (118.69, 34.49, 118.82, 34.59)    # 县城核心区（牛山/石榴街道一带）

COUNTY_ZOOMS = range(10, 16)   # z10–z15
URBAN_ZOOMS = range(16, 19)    # z16–z18

REQUEST_INTERVAL = 0.12        # 每张瓦片间隔（秒），对公共瓦片源友好
TIMEOUT = 30


def _ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def deg2tile(lat, lon, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tile_ranges(bbox, z):
    """返回 (x_min, x_max, y_min, y_max)（含端点）。"""
    w, s, e, n = bbox
    x_min, y_min = deg2tile(n, w, z)   # 左上
    x_max, y_max = deg2tile(s, e, z)   # 右下
    if x_min > x_max:
        x_min, x_max = x_max, x_min
    if y_min > y_max:
        y_min, y_max = y_max, y_min
    return x_min, x_max, y_min, y_max


def count_tiles(plan):
    total = 0
    for bbox, zooms in plan:
        for z in zooms:
            x0, x1, y0, y1 = tile_ranges(bbox, z)
            total += (x1 - x0 + 1) * (y1 - y0 + 1)
    return total


def fetch_tile(z, x, y, ctx, url_idx):
    url = TILE_URLS[url_idx % len(TILE_URLS)].format(z=z, x=x, y=y)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'DonghaiTrafficApp/1.0 (offline county map; contact: local admin)',
        'Accept': 'image/png,image/*;q=0.8,*/*;q=0.5',
        'Referer': 'http://127.0.0.1/',
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return resp.read()


def download_plan(plan):
    ctx = _ctx()
    total = count_tiles(plan)
    print(f'[计划] 共需 {total} 张瓦片（已存在的会自动跳过）')
    done = skipped = failed = 0
    idx = 0
    for bbox, zooms in plan:
        for z in zooms:
            x0, x1, y0, y1 = tile_ranges(bbox, z)
            for x in range(x0, x1 + 1):
                sub = os.path.join(TILES_DIR, str(z), str(x))
                os.makedirs(sub, exist_ok=True)
                for y in range(y0, y1 + 1):
                    fp = os.path.join(sub, f'{y}.png')
                    if os.path.exists(fp) and os.path.getsize(fp) > 0:
                        skipped += 1
                        continue
                    ok = False
                    for attempt in range(len(TILE_URLS)):
                        try:
                            data = fetch_tile(z, x, y, ctx, idx + attempt)
                            if data and len(data) > 100:
                                with open(fp, 'wb') as f:
                                    f.write(data)
                                done += 1
                                ok = True
                                break
                        except Exception:
                            time.sleep(0.3)
                    idx += 1
                    if not ok:
                        failed += 1
                    if (done + skipped + failed) % 200 == 0:
                        pct = (done + skipped + failed) * 100 // max(total, 1)
                        print(f'  进度 {pct}%  新增 {done} / 跳过 {skipped} / 失败 {failed}')
                    time.sleep(REQUEST_INTERVAL)
    return done, skipped, failed


def dir_size_mb(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / 1024 / 1024


def main():
    os.makedirs(TILES_DIR, exist_ok=True)
    plan = [
        (COUNTY_BBOX, COUNTY_ZOOMS),
        (URBAN_BBOX, URBAN_ZOOMS),
    ]
    print('=== 东海县离线地图瓦片下载（街道级）===')
    print('全县 z10-15 + 县城核心区 z16-18')
    done, skipped, failed = download_plan(plan)
    size = dir_size_mb(TILES_DIR)
    print('\n=== 完成 ===')
    print(f'新增 {done} 张，跳过 {skipped} 张，失败 {failed} 张')
    print(f'tiles/ 目录当前约 {size:.0f} MB')
    if failed:
        print('部分瓦片失败多为网络波动，重跑本脚本即可续传补齐。')
    print('把整个 tiles/ 目录连同程序拷到离线机（放在 exe 同级目录）即可。')


if __name__ == '__main__':
    main()
