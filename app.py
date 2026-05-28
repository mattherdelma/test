"""道路交通事故统计与可视化分析系统 - 主程序"""
import os
import io
import sys
import json
import uuid
import shutil
import webbrowser
import threading
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, jsonify, send_file, send_from_directory, abort
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from database import (
    init_db, get_db, DB_PATH, DB_DIR,
    get_dict_options, get_all_dicts, log_action,
)
from report_generator import (
    export_accidents_excel, export_monthly_report_docx,
    build_import_template, parse_import_file,
)

# 打包后：资源 (templates/static) 在 _MEIPASS，可写目录 (data/uploads/backup) 在 exe 旁
if getattr(sys, 'frozen', False):
    RES_DIR = sys._MEIPASS
    BASE_DIR = os.path.dirname(sys.executable)
else:
    RES_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = RES_DIR

UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
BACKUP_DIR = os.path.join(BASE_DIR, 'backup')

app = Flask(__name__,
            template_folder=os.path.join(RES_DIR, 'templates'),
            static_folder=os.path.join(RES_DIR, 'static'))
app.secret_key = 'traffic-accident-local-app-secret-key-change-me'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024


@app.template_filter('from_json')
def _from_json(v):
    if not v:
        return []
    try:
        return json.loads(v)
    except Exception:
        return []


# ============ 工具 ============

def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return wrap


def role_required(*roles):
    def deco(f):
        @wraps(f)
        def wrap(*a, **kw):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('权限不足', 'error')
                return redirect(url_for('dashboard'))
            return f(*a, **kw)
        return wrap
    return deco


@app.context_processor
def inject_globals():
    return {
        'current_user': {
            'id': session.get('user_id'),
            'username': session.get('username'),
            'name': session.get('name'),
            'role': session.get('role'),
        },
        'now': datetime.now,
    }


# ============ 登录登出 ============

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        with get_db() as conn:
            row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if row and check_password_hash(row['password_hash'], password):
            session['user_id'] = row['id']
            session['username'] = row['username']
            session['name'] = row['name']
            session['role'] = row['role']
            log_action(row['id'], row['username'], '登录', '')
            return redirect(url_for('dashboard'))
        flash('用户名或密码错误', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_action(session['user_id'], session['username'], '登出', '')
    session.clear()
    return redirect(url_for('login'))


# ============ 仪表盘 ============

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')


@app.route('/api/dashboard/summary')
@login_required
def api_summary():
    months = int(request.args.get('months', 12))
    end = datetime.now()
    start = (end - timedelta(days=30 * months)).strftime('%Y-%m-%d 00:00')
    with get_db() as conn:
        cur = conn.execute('''
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(death_count),0) AS deaths,
                   COALESCE(SUM(injury_count),0) AS injuries,
                   COALESCE(SUM(economic_loss),0) AS loss
            FROM accidents WHERE occur_time>=?
        ''', (start,))
        cur_row = cur.fetchone()
        prev_start = (end - timedelta(days=30 * months * 2)).strftime('%Y-%m-%d 00:00')
        prev_end = start
        prev = conn.execute('''
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(death_count),0) AS deaths,
                   COALESCE(SUM(injury_count),0) AS injuries,
                   COALESCE(SUM(economic_loss),0) AS loss
            FROM accidents WHERE occur_time>=? AND occur_time<?
        ''', (prev_start, prev_end)).fetchone()

    def yoy(a, b):
        if not b:
            return None
        return round((a - b) / b * 100, 1)

    return jsonify({
        'total': cur_row['total'],
        'deaths': cur_row['deaths'],
        'injuries': cur_row['injuries'],
        'loss': round(cur_row['loss'], 2),
        'total_yoy': yoy(cur_row['total'], prev['total']),
        'deaths_yoy': yoy(cur_row['deaths'], prev['deaths']),
        'injuries_yoy': yoy(cur_row['injuries'], prev['injuries']),
        'loss_yoy': yoy(cur_row['loss'], prev['loss']),
    })


@app.route('/api/dashboard/trend')
@login_required
def api_trend():
    months = int(request.args.get('months', 12))
    end = datetime.now().replace(day=1)
    buckets = []
    for i in range(months - 1, -1, -1):
        d = end - timedelta(days=30 * i)
        buckets.append(d.strftime('%Y-%m'))
    with get_db() as conn:
        rows = conn.execute('''
            SELECT substr(occur_time,1,7) AS ym,
                   COUNT(*) AS c,
                   SUM(death_count) AS d,
                   SUM(injury_count) AS j
            FROM accidents
            WHERE substr(occur_time,1,7) >= ?
            GROUP BY ym ORDER BY ym
        ''', (buckets[0],)).fetchall()
    data = {r['ym']: (r['c'], r['d'] or 0, r['j'] or 0) for r in rows}
    return jsonify({
        'months': buckets,
        'counts': [data.get(m, (0, 0, 0))[0] for m in buckets],
        'deaths': [data.get(m, (0, 0, 0))[1] for m in buckets],
        'injuries': [data.get(m, (0, 0, 0))[2] for m in buckets],
    })


@app.route('/api/dashboard/distribution')
@login_required
def api_distribution():
    field = request.args.get('field', 'type')
    allowed = {'type', 'level', 'cause', 'weather', 'road_type', 'road_condition', 'district'}
    if field not in allowed:
        field = 'type'
    months = int(request.args.get('months', 12))
    start = (datetime.now() - timedelta(days=30 * months)).strftime('%Y-%m-%d 00:00')
    with get_db() as conn:
        rows = conn.execute(f'''
            SELECT {field} AS name, COUNT(*) AS count
            FROM accidents WHERE occur_time>=? AND {field} IS NOT NULL AND {field} != ''
            GROUP BY {field} ORDER BY count DESC
        ''', (start,)).fetchall()
    return jsonify([{'name': r['name'], 'count': r['count']} for r in rows])


@app.route('/api/dashboard/top-roads')
@login_required
def api_top_roads():
    months = int(request.args.get('months', 12))
    limit = int(request.args.get('limit', 10))
    start = (datetime.now() - timedelta(days=30 * months)).strftime('%Y-%m-%d 00:00')
    with get_db() as conn:
        rows = conn.execute('''
            SELECT road_name AS name, COUNT(*) AS count,
                   COALESCE(SUM(death_count),0) AS deaths,
                   COALESCE(SUM(injury_count),0) AS injuries
            FROM accidents WHERE occur_time>=? AND road_name IS NOT NULL AND road_name != ''
            GROUP BY road_name ORDER BY count DESC LIMIT ?
        ''', (start, limit)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/dashboard/heatmap')
@login_required
def api_heatmap():
    """24小时 × 7星期 热力图"""
    months = int(request.args.get('months', 12))
    start = (datetime.now() - timedelta(days=30 * months)).strftime('%Y-%m-%d 00:00')
    with get_db() as conn:
        rows = conn.execute('''
            SELECT occur_time FROM accidents WHERE occur_time>=?
        ''', (start,)).fetchall()
    matrix = [[0] * 24 for _ in range(7)]
    for r in rows:
        try:
            t = datetime.strptime(r['occur_time'][:16], '%Y-%m-%d %H:%M')
            matrix[t.weekday()][t.hour] += 1
        except Exception:
            continue
    data = []
    for d in range(7):
        for h in range(24):
            data.append([h, d, matrix[d][h]])
    return jsonify({
        'data': data,
        'max': max((c for _, _, c in data), default=0),
    })


@app.route('/api/dashboard/casualty')
@login_required
def api_casualty():
    """各等级死伤对比"""
    months = int(request.args.get('months', 12))
    start = (datetime.now() - timedelta(days=30 * months)).strftime('%Y-%m-%d 00:00')
    with get_db() as conn:
        rows = conn.execute('''
            SELECT level AS name,
                   COALESCE(SUM(death_count),0) AS deaths,
                   COALESCE(SUM(injury_count),0) AS injuries
            FROM accidents WHERE occur_time>=? AND level IS NOT NULL
            GROUP BY level
        ''', (start,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/dashboard/map')
@login_required
def api_map():
    """事故地理分布：散点 + 中心点 + 边界"""
    months = int(request.args.get('months', 12))
    start = (datetime.now() - timedelta(days=30 * months)).strftime('%Y-%m-%d 00:00')
    with get_db() as conn:
        rows = conn.execute('''
            SELECT id, accident_no, occur_time, level, type,
                   road_name, road_section, district,
                   longitude, latitude, death_count, injury_count
            FROM accidents
            WHERE occur_time>=? AND longitude IS NOT NULL AND latitude IS NOT NULL
                  AND longitude > 0 AND latitude > 0
            ORDER BY occur_time DESC LIMIT 5000
        ''', (start,)).fetchall()
    points = []
    sum_lon, sum_lat = 0.0, 0.0
    for r in rows:
        points.append({
            'id': r['id'],
            'name': f"{r['accident_no']} {r['road_name'] or ''}",
            'value': [r['longitude'], r['latitude'], (r['death_count'] or 0) * 10 + (r['injury_count'] or 0) + 1],
            'level': r['level'] or '',
            'type': r['type'] or '',
            'occur_time': r['occur_time'],
            'death': r['death_count'] or 0,
            'injury': r['injury_count'] or 0,
            'road': f"{r['district'] or ''} {r['road_name'] or ''} {r['road_section'] or ''}",
        })
        sum_lon += r['longitude']
        sum_lat += r['latitude']
    n = len(points) or 1
    return jsonify({
        'points': points,
        'center': [sum_lon / n, sum_lat / n] if points else [104, 35],
        'count': len(points),
    })


# ============ 事故列表 ============

@app.route('/accidents')
@login_required
def accident_list():
    page = int(request.args.get('page', 1))
    page_size = 20
    filters = {
        'kw': request.args.get('kw', '').strip(),
        'level': request.args.get('level', ''),
        'type': request.args.get('type', ''),
        'district': request.args.get('district', ''),
        'start_date': request.args.get('start_date', ''),
        'end_date': request.args.get('end_date', ''),
    }
    where = []
    params = []
    if filters['kw']:
        where.append('(accident_no LIKE ? OR road_name LIKE ? OR handler LIKE ?)')
        like = f"%{filters['kw']}%"
        params += [like, like, like]
    for k in ('level', 'type', 'district'):
        if filters[k]:
            where.append(f'{k}=?')
            params.append(filters[k])
    if filters['start_date']:
        where.append('occur_time>=?')
        params.append(filters['start_date'] + ' 00:00')
    if filters['end_date']:
        where.append('occur_time<=?')
        params.append(filters['end_date'] + ' 23:59')
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    with get_db() as conn:
        total = conn.execute(f'SELECT COUNT(*) AS c FROM accidents {where_sql}', params).fetchone()['c']
        rows = conn.execute(f'''
            SELECT * FROM accidents {where_sql}
            ORDER BY occur_time DESC LIMIT ? OFFSET ?
        ''', params + [page_size, (page - 1) * page_size]).fetchall()
    total_pages = max(1, (total + page_size - 1) // page_size)
    return render_template(
        'accident_list.html',
        rows=rows, total=total, page=page, total_pages=total_pages,
        filters=filters, dicts=get_all_dicts(),
    )


@app.route('/accidents/new', methods=['GET', 'POST'])
@role_required('admin', 'recorder')
def accident_new():
    if request.method == 'POST':
        return _save_accident(None)
    return render_template('accident_form.html', acc=None, vehicles=[], persons=[], dicts=get_all_dicts())


@app.route('/accidents/<int:acc_id>')
@login_required
def accident_detail(acc_id):
    with get_db() as conn:
        acc = conn.execute('SELECT * FROM accidents WHERE id=?', (acc_id,)).fetchone()
        if not acc:
            abort(404)
        vehicles = conn.execute('SELECT * FROM vehicles WHERE accident_id=?', (acc_id,)).fetchall()
        persons = conn.execute('SELECT * FROM persons WHERE accident_id=?', (acc_id,)).fetchall()
    return render_template('accident_detail.html', acc=acc, vehicles=vehicles, persons=persons)


@app.route('/accidents/<int:acc_id>/edit', methods=['GET', 'POST'])
@role_required('admin', 'recorder')
def accident_edit(acc_id):
    if request.method == 'POST':
        return _save_accident(acc_id)
    with get_db() as conn:
        acc = conn.execute('SELECT * FROM accidents WHERE id=?', (acc_id,)).fetchone()
        if not acc:
            abort(404)
        vehicles = conn.execute('SELECT * FROM vehicles WHERE accident_id=?', (acc_id,)).fetchall()
        persons = conn.execute('SELECT * FROM persons WHERE accident_id=?', (acc_id,)).fetchall()
    return render_template('accident_form.html', acc=acc, vehicles=vehicles, persons=persons, dicts=get_all_dicts())


@app.route('/accidents/<int:acc_id>/delete', methods=['POST'])
@role_required('admin')
def accident_delete(acc_id):
    with get_db() as conn:
        conn.execute('DELETE FROM accidents WHERE id=?', (acc_id,))
    log_action(session.get('user_id'), session.get('username'), '删除事故', str(acc_id))
    flash('已删除', 'success')
    return redirect(url_for('accident_list'))


def _save_accident(acc_id):
    f = request.form

    def s(k, default=''):
        return (f.get(k) or default).strip() if isinstance(f.get(k), str) else (f.get(k) or default)

    def i(k, default=0):
        try:
            return int(f.get(k) or default)
        except Exception:
            return default

    def fl(k, default=0):
        try:
            return float(f.get(k) or default)
        except Exception:
            return default

    occur_time = s('occur_time')
    if not occur_time:
        flash('发生时间必填', 'error')
        return redirect(request.url)

    accident_no = s('accident_no') or f'JT{datetime.now().strftime("%Y%m%d%H%M%S")}'

    fields = (
        accident_no, occur_time, s('report_time'), s('level'), s('type'),
        s('weather'), s('visibility'), s('district'), s('road_name'),
        s('road_section'), s('mileage'),
        fl('longitude'), fl('latitude'),
        s('road_type'), s('road_shape'), s('road_condition'),
        i('death_count'), i('injury_count'), fl('economic_loss'),
        s('cause'), s('handle_result'), s('handler'), s('remarks'),
    )

    with get_db() as conn:
        if acc_id:
            conn.execute('''
                UPDATE accidents SET
                    accident_no=?, occur_time=?, report_time=?, level=?, type=?,
                    weather=?, visibility=?, district=?, road_name=?,
                    road_section=?, mileage=?, longitude=?, latitude=?,
                    road_type=?, road_shape=?, road_condition=?,
                    death_count=?, injury_count=?, economic_loss=?,
                    cause=?, handle_result=?, handler=?, remarks=?,
                    updated_at=datetime('now','localtime')
                WHERE id=?
            ''', fields + (acc_id,))
            conn.execute('DELETE FROM vehicles WHERE accident_id=?', (acc_id,))
            conn.execute('DELETE FROM persons WHERE accident_id=?', (acc_id,))
            new_id = acc_id
            action = '修改事故'
        else:
            cur = conn.execute('''
                INSERT INTO accidents(
                    accident_no, occur_time, report_time, level, type,
                    weather, visibility, district, road_name,
                    road_section, mileage, longitude, latitude,
                    road_type, road_shape, road_condition,
                    death_count, injury_count, economic_loss,
                    cause, handle_result, handler, remarks, created_by
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', fields + (session.get('user_id'),))
            new_id = cur.lastrowid
            action = '新增事故'

        plates = request.form.getlist('v_plate_no')
        vtypes = request.form.getlist('v_vehicle_type')
        vowners = request.form.getlist('v_owner')
        vinsurance = request.form.getlist('v_insurance')
        vuse = request.form.getlist('v_use_type')
        for i_, p in enumerate(plates):
            if not (p or '').strip():
                continue
            conn.execute('''
                INSERT INTO vehicles(accident_id, plate_no, vehicle_type, owner, insurance, use_type)
                VALUES (?,?,?,?,?,?)
            ''', (new_id, p.strip(),
                  vtypes[i_] if i_ < len(vtypes) else '',
                  vowners[i_] if i_ < len(vowners) else '',
                  vinsurance[i_] if i_ < len(vinsurance) else '',
                  vuse[i_] if i_ < len(vuse) else ''))

        p_names = request.form.getlist('p_name')
        p_ids = request.form.getlist('p_id_card')
        p_genders = request.form.getlist('p_gender')
        p_ages = request.form.getlist('p_age')
        p_years = request.form.getlist('p_driving_years')
        p_drunks = request.form.getlist('p_drunk')
        p_resps = request.form.getlist('p_responsibility')
        p_injs = request.form.getlist('p_injury_level')
        for i_, n in enumerate(p_names):
            if not (n or '').strip():
                continue
            try:
                age = int(p_ages[i_]) if i_ < len(p_ages) and p_ages[i_] else 0
            except Exception:
                age = 0
            try:
                yrs = int(p_years[i_]) if i_ < len(p_years) and p_years[i_] else 0
            except Exception:
                yrs = 0
            conn.execute('''
                INSERT INTO persons(accident_id, name, id_card, gender, age, driving_years, drunk, responsibility, injury_level)
                VALUES (?,?,?,?,?,?,?,?,?)
            ''', (new_id, n.strip(),
                  p_ids[i_] if i_ < len(p_ids) else '',
                  p_genders[i_] if i_ < len(p_genders) else '',
                  age, yrs,
                  1 if (i_ < len(p_drunks) and p_drunks[i_] == '1') else 0,
                  p_resps[i_] if i_ < len(p_resps) else '',
                  p_injs[i_] if i_ < len(p_injs) else ''))

    log_action(session.get('user_id'), session.get('username'), action, accident_no)
    flash('保存成功', 'success')
    return redirect(url_for('accident_detail', acc_id=new_id))


# ============ 统计分析独立页 ============

@app.route('/statistics')
@login_required
def statistics():
    return render_template('statistics.html', dicts=get_all_dicts())


# ============ 字典管理 ============

@app.route('/dictionaries')
@role_required('admin')
def dictionaries():
    return render_template('dictionaries.html', dicts=get_all_dicts())


@app.route('/dictionaries/add', methods=['POST'])
@role_required('admin')
def dict_add():
    category = request.form.get('category', '').strip()
    name = request.form.get('name', '').strip()
    if category and name:
        with get_db() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO dictionaries(category,name,sort_order) VALUES (?,?,?)',
                (category, name, 999)
            )
        flash('已添加', 'success')
    return redirect(url_for('dictionaries'))


@app.route('/dictionaries/delete/<int:dict_id>', methods=['POST'])
@role_required('admin')
def dict_delete(dict_id):
    with get_db() as conn:
        conn.execute('DELETE FROM dictionaries WHERE id=?', (dict_id,))
    return redirect(url_for('dictionaries'))


# ============ 导出 ============

@app.route('/export/excel')
@login_required
def export_excel():
    args = request.args
    where = []
    params = []
    if args.get('start_date'):
        where.append('occur_time>=?')
        params.append(args['start_date'] + ' 00:00')
    if args.get('end_date'):
        where.append('occur_time<=?')
        params.append(args['end_date'] + ' 23:59')
    for k in ('level', 'type', 'district'):
        if args.get(k):
            where.append(f'{k}=?')
            params.append(args[k])
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    with get_db() as conn:
        rows = conn.execute(f'''
            SELECT * FROM accidents {where_sql} ORDER BY occur_time DESC
        ''', params).fetchall()
    buf = export_accidents_excel([dict(r) for r in rows])
    fname = f'事故数据_{datetime.now().strftime("%Y%m%d%H%M")}.xlsx'
    log_action(session.get('user_id'), session.get('username'), '导出Excel', str(len(rows)))
    return send_file(
        buf, as_attachment=True, download_name=fname,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/export/report')
@login_required
def export_report():
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    start = f'{year:04d}-{month:02d}-01 00:00'
    if month == 12:
        end = f'{year+1:04d}-01-01 00:00'
    else:
        end = f'{year:04d}-{month+1:02d}-01 00:00'
    prev_year = year - 1
    prev_start = f'{prev_year:04d}-{month:02d}-01 00:00'
    if month == 12:
        prev_end = f'{prev_year+1:04d}-01-01 00:00'
    else:
        prev_end = f'{prev_year:04d}-{month+1:02d}-01 00:00'

    with get_db() as conn:
        cur = conn.execute('''
            SELECT COUNT(*) AS total, COALESCE(SUM(death_count),0) AS deaths,
                   COALESCE(SUM(injury_count),0) AS injuries,
                   COALESCE(SUM(economic_loss),0) AS loss
            FROM accidents WHERE occur_time>=? AND occur_time<?
        ''', (start, end)).fetchone()
        prev = conn.execute('''
            SELECT COUNT(*) AS total FROM accidents WHERE occur_time>=? AND occur_time<?
        ''', (prev_start, prev_end)).fetchone()
        type_dist = [dict(r) for r in conn.execute('''
            SELECT type AS name, COUNT(*) AS count FROM accidents
            WHERE occur_time>=? AND occur_time<? AND type IS NOT NULL
            GROUP BY type ORDER BY count DESC
        ''', (start, end)).fetchall()]
        cause_dist = [dict(r) for r in conn.execute('''
            SELECT cause AS name, COUNT(*) AS count FROM accidents
            WHERE occur_time>=? AND occur_time<? AND cause IS NOT NULL
            GROUP BY cause ORDER BY count DESC
        ''', (start, end)).fetchall()]
        top_roads = [dict(r) for r in conn.execute('''
            SELECT road_name AS name, COUNT(*) AS count,
                   COALESCE(SUM(death_count),0) AS deaths
            FROM accidents WHERE occur_time>=? AND occur_time<? AND road_name IS NOT NULL
            GROUP BY road_name ORDER BY count DESC LIMIT 10
        ''', (start, end)).fetchall()]
        major = [dict(r) for r in conn.execute('''
            SELECT * FROM accidents WHERE occur_time>=? AND occur_time<?
            AND level IN ('重大事故','特大事故')
            ORDER BY occur_time DESC
        ''', (start, end)).fetchall()]

    summary = {
        'total': cur['total'], 'deaths': cur['deaths'],
        'injuries': cur['injuries'], 'loss': cur['loss'],
        'total_yoy': round((cur['total'] - prev['total']) / prev['total'] * 100, 1) if prev['total'] else None,
    }
    buf = export_monthly_report_docx(year, month, summary, top_roads, type_dist, cause_dist, major)
    fname = f'交通事故月报_{year}年{month:02d}月.docx'
    log_action(session.get('user_id'), session.get('username'), '导出月报', f'{year}-{month:02d}')
    return send_file(
        buf, as_attachment=True, download_name=fname,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


# ============ 图片附件 ============

ALLOWED_IMG_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}


def _photos_list(acc_row):
    try:
        return json.loads(acc_row['photos']) if acc_row['photos'] else []
    except Exception:
        return []


@app.route('/accidents/<int:acc_id>/photos', methods=['POST'])
@role_required('admin', 'recorder')
def photo_upload(acc_id):
    with get_db() as conn:
        acc = conn.execute('SELECT id, photos FROM accidents WHERE id=?', (acc_id,)).fetchone()
        if not acc:
            return jsonify({'ok': False, 'msg': '事故不存在'}), 404
        photos = _photos_list(acc)
        if len(photos) >= 10:
            return jsonify({'ok': False, 'msg': '每条事故最多 10 张图片'}), 400
        files = request.files.getlist('photos')
        added = []
        for f in files:
            if not f or not f.filename:
                continue
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in ALLOWED_IMG_EXT:
                continue
            if len(photos) + len(added) >= 10:
                break
            sub = os.path.join(UPLOAD_DIR, str(acc_id))
            os.makedirs(sub, exist_ok=True)
            new_name = f'{uuid.uuid4().hex}{ext}'
            f.save(os.path.join(sub, new_name))
            added.append(new_name)
        photos.extend(added)
        conn.execute('UPDATE accidents SET photos=?, updated_at=datetime("now","localtime") WHERE id=?',
                     (json.dumps(photos), acc_id))
    log_action(session.get('user_id'), session.get('username'), '上传照片', f'{acc_id} +{len(added)}')
    return jsonify({'ok': True, 'added': added, 'all': photos})


@app.route('/accidents/<int:acc_id>/photos/<name>', methods=['DELETE'])
@role_required('admin', 'recorder')
def photo_delete(acc_id, name):
    name = secure_filename(name)
    with get_db() as conn:
        acc = conn.execute('SELECT id, photos FROM accidents WHERE id=?', (acc_id,)).fetchone()
        if not acc:
            return jsonify({'ok': False}), 404
        photos = _photos_list(acc)
        if name not in photos:
            return jsonify({'ok': False, 'msg': '照片不存在'}), 404
        photos.remove(name)
        conn.execute('UPDATE accidents SET photos=?, updated_at=datetime("now","localtime") WHERE id=?',
                     (json.dumps(photos), acc_id))
        try:
            os.remove(os.path.join(UPLOAD_DIR, str(acc_id), name))
        except OSError:
            pass
    log_action(session.get('user_id'), session.get('username'), '删除照片', f'{acc_id}/{name}')
    return jsonify({'ok': True, 'all': photos})


@app.route('/uploads/<int:acc_id>/<name>')
@login_required
def uploaded_file(acc_id, name):
    name = secure_filename(name)
    sub = os.path.join(UPLOAD_DIR, str(acc_id))
    if not os.path.exists(os.path.join(sub, name)):
        abort(404)
    return send_from_directory(sub, name)


# ============ 批量导入 ============

@app.route('/import', methods=['GET'])
@role_required('admin', 'recorder')
def import_page():
    return render_template('import.html')


@app.route('/import/template')
@role_required('admin', 'recorder')
def import_template():
    buf = build_import_template()
    return send_file(
        buf, as_attachment=True, download_name='事故批量导入模板.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/import/upload', methods=['POST'])
@role_required('admin', 'recorder')
def import_upload():
    f = request.files.get('file')
    if not f or not f.filename:
        flash('请选择文件', 'error')
        return redirect(url_for('import_page'))
    if not f.filename.lower().endswith(('.xlsx', '.xls')):
        flash('请上传 Excel 文件 (.xlsx)', 'error')
        return redirect(url_for('import_page'))
    try:
        records, errors = parse_import_file(f.stream)
    except Exception as e:
        flash(f'解析失败: {e}', 'error')
        return redirect(url_for('import_page'))

    ok_count = 0
    with get_db() as conn:
        for rec in records:
            try:
                if not rec.get('accident_no'):
                    rec['accident_no'] = f'JT{datetime.now().strftime("%Y%m%d%H%M%S")}{ok_count:03d}'
                conn.execute('''
                    INSERT INTO accidents(
                        accident_no, occur_time, report_time, level, type,
                        weather, visibility, district, road_name, road_section,
                        mileage, longitude, latitude, road_type, road_shape, road_condition,
                        death_count, injury_count, economic_loss,
                        cause, handle_result, handler, remarks, created_by
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (
                    rec['accident_no'], rec['occur_time'], rec.get('report_time', ''),
                    rec.get('level', ''), rec.get('type', ''),
                    rec.get('weather', ''), rec.get('visibility', ''),
                    rec.get('district', ''), rec.get('road_name', ''),
                    rec.get('road_section', ''), rec.get('mileage', ''),
                    rec.get('longitude', 0) or 0, rec.get('latitude', 0) or 0,
                    rec.get('road_type', ''), rec.get('road_shape', ''),
                    rec.get('road_condition', ''),
                    rec.get('death_count', 0) or 0, rec.get('injury_count', 0) or 0,
                    rec.get('economic_loss', 0) or 0,
                    rec.get('cause', ''), rec.get('handle_result', ''),
                    rec.get('handler', ''), rec.get('remarks', ''),
                    session.get('user_id'),
                ))
                ok_count += 1
            except Exception as e:
                errors.append({'row': rec.get('_row'), 'msg': f'写入失败: {e}'})

    log_action(session.get('user_id'), session.get('username'),
               '批量导入', f'成功 {ok_count} / 失败 {len(errors)}')
    return render_template('import.html', result={
        'ok_count': ok_count,
        'errors': errors,
        'total': len(records) + (len(errors) - sum(1 for e in errors if 'row' in e and e.get('msg', '').startswith('写入失败'))),
    })


# ============ 用户管理 ============

@app.route('/users')
@role_required('admin')
def user_list():
    with get_db() as conn:
        users = conn.execute('SELECT * FROM users ORDER BY id').fetchall()
        logs = conn.execute(
            'SELECT * FROM operation_logs ORDER BY id DESC LIMIT 50'
        ).fetchall()
    return render_template('users.html', users=users, logs=logs)


@app.route('/users/add', methods=['POST'])
@role_required('admin')
def user_add():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    name = request.form.get('name', '').strip()
    role = request.form.get('role', 'recorder')
    if not (username and password):
        flash('用户名密码必填', 'error')
        return redirect(url_for('user_list'))
    try:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO users(username,password_hash,role,name) VALUES (?,?,?,?)',
                (username, generate_password_hash(password), role, name)
            )
        flash('添加成功', 'success')
    except Exception as e:
        flash(f'添加失败: {e}', 'error')
    return redirect(url_for('user_list'))


@app.route('/users/<int:uid>/reset', methods=['POST'])
@role_required('admin')
def user_reset(uid):
    new_pw = request.form.get('password', '').strip()
    if not new_pw:
        flash('请输入新密码', 'error')
        return redirect(url_for('user_list'))
    with get_db() as conn:
        conn.execute('UPDATE users SET password_hash=? WHERE id=?',
                     (generate_password_hash(new_pw), uid))
    flash('密码已重置', 'success')
    return redirect(url_for('user_list'))


@app.route('/users/<int:uid>/delete', methods=['POST'])
@role_required('admin')
def user_delete(uid):
    if uid == session.get('user_id'):
        flash('不能删除自己', 'error')
        return redirect(url_for('user_list'))
    with get_db() as conn:
        conn.execute('DELETE FROM users WHERE id=?', (uid,))
    return redirect(url_for('user_list'))


# ============ 备份与恢复 ============

@app.route('/backup', methods=['POST'])
@role_required('admin')
def backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    fname = f'accidents_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
    dst = os.path.join(BACKUP_DIR, fname)
    shutil.copy2(DB_PATH, dst)
    log_action(session.get('user_id'), session.get('username'), '备份数据库', fname)
    flash(f'备份完成: {fname}', 'success')
    return redirect(url_for('user_list'))


# ============ 启动 ============

def auto_backup():
    """启动时自动备份，保留 30 天"""
    if not os.path.exists(DB_PATH):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    today = datetime.now().strftime('%Y%m%d')
    dst = os.path.join(BACKUP_DIR, f'auto_{today}.db')
    if not os.path.exists(dst):
        shutil.copy2(DB_PATH, dst)
    cutoff = datetime.now() - timedelta(days=30)
    for f in os.listdir(BACKUP_DIR):
        full = os.path.join(BACKUP_DIR, f)
        try:
            if datetime.fromtimestamp(os.path.getmtime(full)) < cutoff:
                os.remove(full)
        except Exception:
            pass


def open_browser():
    webbrowser.open('http://127.0.0.1:5000/')


if __name__ == '__main__':
    init_db()
    auto_backup()
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        threading.Timer(1.2, open_browser).start()
    app.run(host='127.0.0.1', port=5000, debug=False)
