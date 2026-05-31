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
  · 东海县县界用 320722.json（不带 _full；带 _full 会 404，因东海县无公开乡镇级边界）。
  · 万一县级接口失败，会自动从连云港市 320700_full.json 中抽取东海县那一块兜底。
- 路网数据来自 OpenStreetMap（ODbL 协议），通过 Overpass API 抓取（街道/道路级）。
  · 每个镜像先按行政区名精确抓取，再按外接矩形兜底，并修正了部分镜像 406 的请求头问题。
- 若某一项下载失败不影响其它项；donghai.json 失败时保留内置占位县界，程序仍可运行。
- 路网文件可能有几 MB，属正常。

注意：本系统为离线单机应用，地图用「可下载的 GeoJSON（边界+路网）」而非在线瓦片，
      因此无需任何地图服务密钥，且部署到无外网的内网机器后地图依然可用。
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

# DataV 边界数据源：
#   {code}.json       仅该行政区自身边界（东海县用这个 → 真实县界）
#   {code}_full.json  含下一级行政区划（连云港市用这个 → 含各区县，其中有东海县）
# 注意：东海县没有公开的乡镇级边界，故 320722_full.json 会 404，必须用不带 _full 的。
DATAV = 'https://geo.datav.aliyun.com/areas_v3/bound/{code}.json'
DATAV_FULL = 'https://geo.datav.aliyun.com/areas_v3/bound/{code}_full.json'

# GitHub 镜像（datav 在部分内网/代理下返回 403 时的可靠兜底）：
# longwosion/geojson-map-china 的 geometryCouties/{市码}.json 含该市各区县真实边界。
GITHUB_CITY_COUNTIES = ('https://raw.githubusercontent.com/longwosion/'
                        'geojson-map-china/master/geometryCouties/{code}.json')

# Overpass 镜像，按顺序尝试（不同镜像对 Accept/UA 头要求不一，故统一带规范请求头）
OVERPASS_ENDPOINTS = [
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass-api.de/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
    'https://overpass.openstreetmap.ru/api/interpreter',
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


def _fetch(url, ctx, data=None, timeout=180, extra_headers=None):
    headers = {
        # 用描述性 UA + Accept:application/json；overpass-api.de 对伪装浏览器 UA 会回 406
        'User-Agent': 'donghai-traffic-app/1.0 (county road import)',
        'Accept': 'application/json',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        url,
        data=data.encode('utf-8') if isinstance(data, str) else data,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()


def _is_placeholder(path):
    """判断现有 donghai.json 是否为内置占位边界（带 _note 字段）。"""
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return '_note' in d  # 占位文件特有标记
    except Exception:
        return True


def download_city(code, out_name, label):
    """下载市级 _full 边界（含各区县）。返回解析后的 GeoJSON 或 None。"""
    out = os.path.join(MAP_DIR, out_name)
    url = DATAV_FULL.format(code=code)
    try:
        print(f'[下载] {label} 边界: {url}')
        raw = _fetch(url, _ctx(), timeout=60)
        geo = json.loads(raw)
        if not geo.get('features'):
            print(f'  [警告] {label} 返回数据为空')
            return None
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(geo, f, ensure_ascii=False)
        print(f'  [完成] {out_name}  {len(geo["features"])} 个区划  {len(raw)//1024} KB')
        return geo
    except Exception as e:
        print(f'  [失败] {label} 边界: {e}')
        return None


def download_county(out_name, label, city_geo):
    """下载东海县县界：先用不带 _full 的官方接口，失败则从市级数据中抽取东海县。"""
    out = os.path.join(MAP_DIR, out_name)
    if os.path.exists(out) and not _is_placeholder(out):
        print(f'[跳过] {label} 边界已存在真实数据: {out_name}')
        return True

    # 方案A：官方县级接口（真实县界）
    url = DATAV.format(code=REGION_CODE)
    try:
        print(f'[下载] {label} 边界: {url}')
        raw = _fetch(url, _ctx(), timeout=60)
        geo = json.loads(raw)
        if geo.get('features'):
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(geo, f, ensure_ascii=False)
            print(f'  [完成] {out_name}  真实县界  {len(raw)//1024} KB')
            return True
    except Exception as e:
        print(f'  [失败] 县级接口: {e}，尝试从连云港市数据中抽取…')

    # 方案B：从市级 _full 里抽出东海县那一块（adcode==320722）
    if city_geo and city_geo.get('features'):
        for feat in city_geo['features']:
            props = feat.get('properties', {})
            if str(props.get('adcode')) == REGION_CODE or props.get('name') == '东海县':
                fc = {'type': 'FeatureCollection', 'features': [feat]}
                with open(out, 'w', encoding='utf-8') as f:
                    json.dump(fc, f, ensure_ascii=False)
                print(f'  [完成] {out_name}  （从连云港市数据抽取东海县）')
                return True
        print('  [警告] 连云港市数据中未找到东海县')

    # 方案C：GitHub 镜像（datav 被代理 403 时的可靠兜底）
    url = GITHUB_CITY_COUNTIES.format(code=CITY_CODE)
    try:
        print(f'[下载] {label} 边界(GitHub 兜底): {url}')
        geo = json.loads(_fetch(url, _ctx(), timeout=60))
        for feat in geo.get('features', []):
            props = feat.get('properties', {})
            if str(props.get('id')) == REGION_CODE or props.get('name') == '东海县':
                props['name'] = '东海县'
                props['adcode'] = int(REGION_CODE)
                props.setdefault('center', [118.752, 34.542])
                fc = {'type': 'FeatureCollection', 'features': [feat]}
                with open(out, 'w', encoding='utf-8') as f:
                    json.dump(fc, f, ensure_ascii=False)
                print(f'  [完成] {out_name}  真实县界（GitHub 镜像）')
                return True
    except Exception as e:
        print(f'  [失败] GitHub 兜底: {e}')

    print('  [跳过] 东海县边界获取失败，保留内置占位县界（程序仍可正常运行）')
    return False


def _overpass_query_area():
    # 按行政区名精确抓取东海县境内道路（最准，不含邻县）
    return f"""
[out:json][timeout:240];
area["name"="东海县"]["admin_level"~"6|7|8"]->.dh;
(
  way["highway"~"^({HIGHWAY_TYPES})$"](area.dh);
);
out geom;
"""


def _overpass_query_bbox():
    s, w, n, e = BBOX
    # 兜底：按外接矩形抓取（可能含少量邻县道路，但保证有数据）
    return f"""
[out:json][timeout:240];
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
    # 每个镜像先试 area 精确查询，再试 bbox 兜底
    attempts = [(ep, q, qn)
                for ep in OVERPASS_ENDPOINTS
                for q, qn in ((_overpass_query_area(), 'area'),
                              (_overpass_query_bbox(), 'bbox'))]
    for ep, query, qn in attempts:
        try:
            print(f'[下载] 路网(OSM,{qn}): {ep}')
            raw = _fetch(ep, _ctx(),
                         data='data=' + urllib.parse.quote(query),
                         timeout=240,
                         extra_headers={'Content-Type': 'application/x-www-form-urlencoded'})
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
                print('  [警告] 未解析到道路，换下一种方式')
                continue
            geo = {'type': 'FeatureCollection', 'features': features}
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(geo, f, ensure_ascii=False)
            size = os.path.getsize(out)
            print(f'  [完成] donghai_roads.json  {len(features)} 条道路  {size//1024} KB')
            return True
        except Exception as ex:
            print(f'  [失败] {ep}({qn}): {ex}')
            time.sleep(2)
    print('  [跳过] 路网下载失败（可稍后重试）。不影响其它功能，驾驶舱仅不显示底层路网。')
    return False


def main():
    os.makedirs(MAP_DIR, exist_ok=True)
    print('=== 东海县地图数据下载 ===')
    # 先下连云港市（含各区县），既用于「连云港市」视图，也作东海县县界的兜底来源
    city_geo = download_city(CITY_CODE, 'lianyungang.json', '连云港市')
    ok1 = download_county('donghai.json', '东海县', city_geo)
    ok2 = city_geo is not None
    ok3 = download_roads()
    print('\n=== 完成 ===')
    print(f'东海县边界: {"✓" if ok1 else "× (保留占位边界)"}')
    print(f'连云港边界: {"✓" if ok2 else "×"}')
    print(f'东海县路网: {"✓ (街道级)" if ok3 else "×"}')
    if not (ok1 and ok3):
        print('\n提示：如失败多为网络/镜像波动，可重试几次；或在能访问外网的机器上运行后拷贝 static/js/maps/ 目录。')


if __name__ == '__main__':
    main()
