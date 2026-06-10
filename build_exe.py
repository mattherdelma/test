"""一键打包 EXE：跨平台调用 PyInstaller"""
import os
import sys
import shutil
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
SEP = ';' if os.name == 'nt' else ':'

DIST_NAME = '道路交通事故统计与可视化分析系统'


def ensure_dependencies():
    try:
        import PyInstaller  # noqa
    except ImportError:
        print('PyInstaller 未安装，正在安装...')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                               'pyinstaller', '-i', 'https://pypi.tuna.tsinghua.edu.cn/simple'])


def ensure_echarts():
    p = os.path.join(ROOT, 'static', 'js', 'echarts.min.js')
    if not os.path.exists(p) or os.path.getsize(p) < 100000:
        print('ECharts 缺失，先运行 download_libs.py...')
        subprocess.check_call([sys.executable, os.path.join(ROOT, 'download_libs.py')])


def clean():
    for d in ('build', 'dist', '__pycache__'):
        full = os.path.join(ROOT, d)
        if os.path.exists(full):
            print(f'[清理] {full}')
            shutil.rmtree(full, ignore_errors=True)
    for f in os.listdir(ROOT):
        if f.endswith('.spec'):
            os.remove(os.path.join(ROOT, f))


def build():
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--clean',
        '--onefile',
        '--name', DIST_NAME,
        f'--add-data=templates{SEP}templates',
        f'--add-data=static{SEP}static',
        '--hidden-import', 'openpyxl',
        '--hidden-import', 'openpyxl.cell._writer',
        '--hidden-import', 'docx',
        '--hidden-import', 'sqlite3',
        'app.py',
    ]
    print('[执行] ' + ' '.join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def post_pack():
    """把 README、run-after-build 等附进 dist/"""
    dist = os.path.join(ROOT, 'dist')
    if not os.path.exists(dist):
        return
    # 在 dist 里也带一份说明
    readme = os.path.join(dist, '使用说明.txt')
    with open(readme, 'w', encoding='utf-8') as f:
        f.write(
            '道路交通事故统计与可视化分析系统\n'
            '================================\n\n'
            '使用方法：\n'
            f'  1. 双击 "{DIST_NAME}.exe"\n'
            '  2. 浏览器会自动打开 http://127.0.0.1:5000\n'
            '  3. 初始账号：admin / admin123\n\n'
            '注意：\n'
            '  · 首次启动会在 exe 旁创建 data/、uploads/、backup/ 目录\n'
            '  · 不要移动 exe 后单独运行，请连同同目录数据一并保留\n'
            '  · 数据文件 data/accidents.db 是关键文件，请定期备份\n'
        )
    print(f'[完成] {dist}')
    for f in os.listdir(dist):
        full = os.path.join(dist, f)
        size = os.path.getsize(full)
        print(f'  - {f}  ({size / 1024 / 1024:.1f} MB)' if size > 1024 * 1024 else f'  - {f}')


if __name__ == '__main__':
    if '--clean' in sys.argv:
        clean()
        sys.exit(0)
    ensure_dependencies()
    ensure_echarts()
    clean()
    build()
    post_pack()
    print('\n打包完成！可执行文件在 dist/ 目录。')
