"""
下载东海县地图数据，实现离线街道/道路级可视化。

在「能联网」的机器上运行一次即可（之后整个目录拷到内网单机使用）：

    python download_donghai_map.py

会生成三份文件到 static/js/maps/ ：
  1. donghai.json        东海县各街道/乡镇真实边界（官方 DataV，行政区划码 320722）
  2. lianyungang.json    连云港市各区县边界（用于「连云港市」视图）
  3. donghai_roads.json  东海县真实路网（OpenStreetMap，驾驶舱「显示路网」即叠加）

说明：
- 边界数据来自阿里 DataV.GeoAtlas（公开、可商用）。
- 路网数据来自 OpenStreetMap（ODbL 协议），通过 Overpass API 抓取。
- 若某一项下载失败不影响其它项；donghai.json 下载失败时保留原占位边界，程序仍可运行。
- 路网文件可能有几 MB，属正常。
"""
import os
import ssl
import json
import time
import urllib.request
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
MAP_DIR = os.path.join(BASE, 'static', 'js', 'maps')

REGION_CODE = '320722'          # 东海县
CITY_CODE = '320700'            # 连云港市
# 东海县地理范围（南,西,北,东），用于 Overpass bbox 兜底查询
BBOX = (34.30, 118.40, 34.95, 119.08)

# DataV 边界数据源（_full 表示带下一级行政区划）
DATAV = 'https://geo.datav.aliyun.com/areas_v3/bound/{code}_full.json'

# Overpass 镜像，按顺序尝试
OVERPASS_ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
]

# 抓取的道路类型（可按需增删；service/footway 等会让文件暴涨，默认不取）
HIGHWAY_TYPES = (
    'motorway|trunk|primary|secondary|tertiary|unclassified|residential|'
    'living_street|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link'
)


def _ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch(url, ctx, data=None, timeout=180):
    req = urllib.request.Request(
        url,
        data=data.encode('utf-8') if isinstance(data, str) else data,
        headers={'User-Agent': 'Mozilla/5.0 (donghai-traffic-app)'},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()


def download_boundary(code, out_name, label):
    out = os.path.join(MAP_DIR, out_name)
    # 已是真实数据（含多个下级区划）则跳过；占位文件(仅1个feature)会被升级
    if os.path.exists(out):
        try:
            with open(out, encoding='utf-8') as f:
                exist = json.load(f)
            if len(exist.get('features', [])) > 1:
                print(f'[跳过] {label} 边界已存在真实数据: {out_name}')
                return True
        except Exception:
            pass
    url = DATAV.format(code=code)
    try:
        print(f'[下载] {label} 边界: {url}')
        raw = _fetch(url, _ctx(), timeout=60)
        geo = json.loads(raw)
        if not geo.get('features'):
            print(f'  [警告] {label} 返回数据为空，跳过')
            return False
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(geo, f, ensure_ascii=False)
        print(f'  [完成] {out_name}  {len(geo["features"])} 个区划  {len(raw)//1024} KB')
        return True
    except Exception as e:
        print(f'  [失败] {label} 边界: {e}')
        return False


def _overpass_query():
    s, w, n, e = BBOX
    # 优先按行政区域名抓取，bbox 作为范围约束，避免抓到邻县
    return f"""
[out:json][timeout:180];
(
  way["highway"~"^({HIGHWAY_TYPES})$"]({s},{w},{n},{e});
);
out geom;
"""


def download_roads():
    out = os.path.join(MAP_DIR, 'donghai_roads.json')
    if os.path.exists(out) and os.path.getsize(out) > 1024:
        print(f'[跳过] 路网已存在: donghai_roads.json')
        return True
    query = _overpass_query()
    for ep in OVERPASS_ENDPOINTS:
        try:
            print(f'[下载] 路网(OSM): {ep}')
            raw = _fetch(ep, _ctx(), data='data=' + urllib.parse.quote(query), timeout=240)
            data = json.loads(raw)
            elements = data.get('elements', [])
            features = []
            for el in elements:
                if el.get('type') != 'way' or 'geometry' not in el:
                    continue
                coords = [[round(p['lon'], 6), round(p['lat'], 6)] for p in el['geometry']]
                if len(coords) < 2:
                    continue
                tags = el.get('tags', {})
                features.append({
                    'type': 'Feature',
                    'properties': {
                        'name': tags.get('name', ''),
                        'highway': tags.get('highway', ''),
                    },
                    'geometry': {'type': 'LineString', 'coordinates': coords},
                })
            if not features:
                print('  [警告] 未解析到道路，换下一个镜像')
                continue
            geo = {'type': 'FeatureCollection', 'features': features}
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(geo, f, ensure_ascii=False)
            size = os.path.getsize(out)
            print(f'  [完成] donghai_roads.json  {len(features)} 条道路  {size//1024} KB')
            return True
        except Exception as ex:
            print(f'  [失败] {ep}: {ex}')
            time.sleep(2)
    print('  [跳过] 路网下载失败（可稍后重试）。不影响其它功能，驾驶舱仅不显示底层路网。')
    return False


def main():
    os.makedirs(MAP_DIR, exist_ok=True)
    print('=== 东海县地图数据下载 ===')
    ok1 = download_boundary(REGION_CODE, 'donghai.json', '东海县')
    ok2 = download_boundary(CITY_CODE, 'lianyungang.json', '连云港市')
    ok3 = download_roads()
    print('\n=== 完成 ===')
    print(f'东海县边界: {"✓" if ok1 else "× (保留占位边界)"}')
    print(f'连云港边界: {"✓" if ok2 else "×"}')
    print(f'东海县路网: {"✓" if ok3 else "×"}')
    if not (ok1 and ok3):
        print('\n提示：如全部失败，多为网络/镜像波动，可重试几次；或在能访问外网的机器上运行后拷贝 static/js/maps/ 目录。')


if __name__ == '__main__':
    main()
