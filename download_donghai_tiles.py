"""
下载东海县离线地图瓦片（天地图官方源），实现可缩放、逐层看街道细节的离线底图。

在【能联网】的机器上运行一次（之后把生成的 tiles/ 目录连同程序一起拷到离线机）：

    python download_donghai_tiles.py

瓦片来源：天地图（国家地理信息公共服务平台，tianditu.gov.cn）。
  · 底图 vec_w（矢量路网）+ 注记 cva_w（中文地名/道路名），下载时合成为一张 PNG。
  · 已内置应用密钥（tk）。如更换单位自有密钥，改 TIANDITU_KEY 即可。
  · 合规：天地图允许在标注来源（GS(2023)336号 等）前提下使用，适合政务离线场景。

策略（约 1.7 万张瓦片 / 约 300MB，天地图最高到 z18）：
  · 全县范围      z10–z15   能看到县域、乡镇、主次干道到街道
  · 县城核心区    z16–z18   牛山/石榴街道一带，能看到小巷、建筑轮廓
  说明：z18 是天地图（及绝大多数免费合法源）能提供的最精级别，已是“小巷/楼栋轮廓”级；
       真正的“门牌级”(z19-20)免费合法源普遍不提供，故封顶到 z18。

瓦片保存为   tiles/{z}/{x}/{y}.png   ，程序通过 /tiles/{z}/{x}/{y}.png 离线读取。
脚本可断点续传（已存在的瓦片自动跳过），中断后重跑即可继续。
"""
import os
import ssl
import math
import time
import io
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
TILES_DIR = os.path.join(BASE, 'tiles')

# ===== 天地图配置 =====
# 应用密钥（tk）。如有单位自有密钥，替换此处即可。
TIANDITU_KEY = 'e9d74ee846368229ada96a20350596a3'
# 子域 t0..t7 轮询，分摊压力、提速
SUBDOMAINS = [str(i) for i in range(8)]
# 底图(vec_w) + 注记(cva_w)。注记层背景透明，叠加到底图上得到带中文地名的成图。
BASE_LAYER = 'vec_w'    # 矢量底图（路网/水系/绿地）
ANNO_LAYER = 'cva_w'    # 中文注记（地名/道路名）
WITH_LABELS = True      # True=合成中文注记（推荐）；False=只下底图，下载量减半
TIANDITU_TPL = ('https://t{s}.tianditu.gov.cn/DataServer'
                '?T={layer}&x={x}&y={y}&l={z}&tk={tk}')

# 下载范围（西, 南, 东, 北）。范围越往高缩放级，框得越小以控制体积。
COUNTY_BBOX = (118.40, 34.30, 119.08, 34.95)   # 东海县全域
URBAN_BBOX = (118.69, 34.49, 118.82, 34.59)    # 县城核心区（牛山/石榴街道一带）

COUNTY_ZOOMS = range(10, 16)   # z10–z15  全县到街道
URBAN_ZOOMS = range(16, 19)    # z16–z18  县城到小巷/楼栋轮廓（天地图封顶）

REQUEST_INTERVAL = 0.08        # 每张瓦片间隔（秒），对天地图友好、避免触发限频
TIMEOUT = 30

# Pillow 仅在【联网下载机】合成注记时需要；离线机不需要。缺失则自动退化为“只底图”。
try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False


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


def _get(layer, z, x, y, ctx, sub_idx):
    """取单层瓦片字节；失败抛异常。"""
    url = TIANDITU_TPL.format(s=SUBDOMAINS[sub_idx % len(SUBDOMAINS)],
                              layer=layer, x=x, y=y, z=z, tk=TIANDITU_KEY)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'DonghaiTrafficApp/1.0 (offline county map)',
        'Accept': 'image/png,image/*;q=0.8,*/*;q=0.5',
        'Referer': 'https://www.tianditu.gov.cn/',
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return resp.read()


def fetch_tile(z, x, y, ctx, sub_idx):
    """取底图(+注记)并合成为单张 PNG 字节。"""
    base = _get(BASE_LAYER, z, x, y, ctx, sub_idx)
    if not base or len(base) < 100:
        raise ValueError('empty base tile')
    if not (WITH_LABELS and HAS_PIL):
        return base
    try:
        anno = _get(ANNO_LAYER, z, x, y, ctx, sub_idx)
        bimg = Image.open(io.BytesIO(base)).convert('RGBA')
        aimg = Image.open(io.BytesIO(anno)).convert('RGBA')
        bimg.alpha_composite(aimg)
        out = io.BytesIO()
        bimg.convert('RGB').save(out, 'PNG')
        return out.getvalue()
    except Exception:
        # 注记层缺失/异常时，至少保留底图，不让整张失败
        return base


def download_plan(plan):
    ctx = _ctx()
    total = count_tiles(plan)
    mode = '底图+中文注记' if (WITH_LABELS and HAS_PIL) else '仅底图'
    if WITH_LABELS and not HAS_PIL:
        print('[提示] 未安装 Pillow，本次只下底图（无地名注记）。'
              '如需中文地名，请在联网机执行: pip install Pillow 后重跑。')
    print(f'[计划] 共需 {total} 张瓦片（{mode}，已存在的会自动跳过）')
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
                    for attempt in range(len(SUBDOMAINS)):
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
    print('=== 东海县离线地图瓦片下载（天地图官方源）===')
    print('全县 z10-15 + 县城核心区 z16-18（天地图封顶 z18）')
    est = count_tiles(plan)
    print(f'预计约 {est} 张瓦片、约 {est*18//1024} MB')
    done, skipped, failed = download_plan(plan)
    size = dir_size_mb(TILES_DIR)
    print('\n=== 完成 ===')
    print(f'新增 {done} 张，跳过 {skipped} 张，失败 {failed} 张')
    print(f'tiles/ 目录当前约 {size:.0f} MB')
    if failed:
        print('部分瓦片失败多为网络波动/限频，等几分钟重跑本脚本即可续传补齐。')
    print('把整个 tiles/ 目录连同程序拷到离线机（放在 exe 同级目录）即可。')


if __name__ == '__main__':
    main()
