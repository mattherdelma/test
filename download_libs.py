"""下载前端依赖（ECharts），实现离线可用。支持多源 + npm tarball 兜底"""
import io
import os
import ssl
import sys
import tarfile
import urllib.request

TARGET = 'static/js/echarts.min.js'
DIRECT_URLS = [
    'https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js',
    'https://unpkg.com/echarts@5.4.3/dist/echarts.min.js',
    'https://npm.elemecdn.com/echarts@5.4.3/dist/echarts.min.js',
]
TARBALL_URL = 'https://registry.npmjs.org/echarts/-/echarts-5.4.3.tgz'


def _fetch(url, ctx):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return resp.read()


def download():
    base = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(base, TARGET)
    if os.path.exists(target) and os.path.getsize(target) > 100000:
        print(f'[跳过] 已存在 {target}')
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for url in DIRECT_URLS:
        try:
            print(f'[下载] {url}')
            data = _fetch(url, ctx)
            if len(data) > 100000:
                with open(target, 'wb') as f:
                    f.write(data)
                print(f'[完成] {target}  {len(data)//1024} KB')
                return
        except Exception as e:
            print(f'  失败: {e}')

    print(f'[兜底] 从 npm 仓库下载 tarball: {TARBALL_URL}')
    try:
        data = _fetch(TARBALL_URL, ctx)
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
            for m in tar.getmembers():
                if m.name.endswith('dist/echarts.min.js'):
                    f = tar.extractfile(m)
                    if f:
                        content = f.read()
                        with open(target, 'wb') as out:
                            out.write(content)
                        print(f'[完成] {target}  {len(content)//1024} KB')
                        return
        print('[错误] tarball 中未找到 echarts.min.js')
    except Exception as e:
        print(f'[错误] tarball 下载失败: {e}')
    sys.exit(1)


# ---- Leaflet（离线瓦片地图引擎，用于东海县街道级可缩放地图）----
LEAFLET_FILES = [
    ('static/js/leaflet.js', [
        'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js',
        'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
        'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js',
    ], 50000),
    ('static/css/leaflet.css', [
        'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css',
        'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
        'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css',
    ], 5000),
    # 热力图插件（可选，缺失时前端自动退回散点）
    ('static/js/leaflet-heat.js', [
        'https://cdn.jsdelivr.net/npm/leaflet.heat@0.2.0/dist/leaflet-heat.js',
        'https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js',
    ], 2000),
]


def download_leaflet():
    base = os.path.dirname(os.path.abspath(__file__))
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for rel, urls, min_size in LEAFLET_FILES:
        target = os.path.join(base, rel)
        if os.path.exists(target) and os.path.getsize(target) >= min_size:
            print(f'[跳过] 已存在 {rel}')
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        got = False
        for url in urls:
            try:
                print(f'[下载] {url}')
                data = _fetch(url, ctx)
                if len(data) >= min_size:
                    with open(target, 'wb') as f:
                        f.write(data)
                    print(f'[完成] {rel}  {len(data)//1024} KB')
                    got = True
                    break
            except Exception as e:
                print(f'  失败: {e}')
        if not got:
            print(f'[警告] {rel} 下载失败（可重试；热力图插件缺失不影响主功能）')


if __name__ == '__main__':
    download()
    download_leaflet()
