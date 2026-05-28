"""导出 Excel 和 Word 月报"""
import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


def export_accidents_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = '事故列表'
    headers = ['事故编号', '发生时间', '等级', '类型', '行政区划', '道路名称', '路段',
               '天气', '路面状况', '死亡', '受伤', '直接损失(元)', '事故原因', '处理结果', '处理民警']
    ws.append(headers)
    head_fill = PatternFill('solid', fgColor='1f4e79')
    head_font = Font(bold=True, color='FFFFFF', size=11)
    thin = Side(border_style='thin', color='cccccc')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for c in ws[1]:
        c.fill = head_fill
        c.font = head_font
        c.alignment = Alignment(horizontal='center', vertical='center')
        c.border = border
    widths = [18, 17, 10, 12, 12, 14, 10, 8, 10, 8, 8, 13, 14, 12, 10]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    for r in rows:
        ws.append([
            r['accident_no'], r['occur_time'], r['level'], r['type'],
            r['district'], r['road_name'], r['road_section'],
            r['weather'], r['road_condition'],
            r['death_count'], r['injury_count'], r['economic_loss'],
            r['cause'], r['handle_result'], r['handler']
        ])
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.border = border
            c.alignment = Alignment(vertical='center')
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def export_monthly_report_docx(year, month, summary, top_roads, type_dist, cause_dist, major_list):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = '宋体'
    style.font.size = Pt(11)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f'{year}年{month}月道路交通事故统计分析报告')
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1f, 0x4e, 0x79)

    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info.add_run(f'报告生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}').font.size = Pt(10)

    doc.add_heading('一、事故总体概况', level=1)
    p = doc.add_paragraph()
    p.add_run(
        f'{year}年{month}月共发生道路交通事故 '
    )
    r = p.add_run(f'{summary["total"]} ')
    r.bold = True
    r.font.color.rgb = RGBColor(0xc0, 0x00, 0x00)
    p.add_run(
        f'起，造成死亡 {summary["deaths"]} 人，受伤 {summary["injuries"]} 人，'
        f'直接经济损失 {summary["loss"]:.2f} 元。'
    )
    if summary.get('total_yoy') is not None:
        yoy = summary['total_yoy']
        trend = '上升' if yoy > 0 else '下降' if yoy < 0 else '持平'
        p.add_run(f'与去年同期相比事故数{trend} {abs(yoy):.1f}%。')

    table = doc.add_table(rows=2, cols=4)
    table.style = 'Light Grid Accent 1'
    h = table.rows[0].cells
    h[0].text = '事故总数(起)'
    h[1].text = '死亡人数(人)'
    h[2].text = '受伤人数(人)'
    h[3].text = '直接损失(元)'
    v = table.rows[1].cells
    v[0].text = str(summary['total'])
    v[1].text = str(summary['deaths'])
    v[2].text = str(summary['injuries'])
    v[3].text = f'{summary["loss"]:.2f}'
    for c in h:
        for r in c.paragraphs:
            for run in r.runs:
                run.bold = True

    doc.add_heading('二、事故类型分布', level=1)
    if type_dist:
        t = doc.add_table(rows=1, cols=3)
        t.style = 'Light Grid Accent 1'
        hdr = t.rows[0].cells
        hdr[0].text = '事故类型'
        hdr[1].text = '数量(起)'
        hdr[2].text = '占比(%)'
        total = sum(x['count'] for x in type_dist) or 1
        for x in type_dist:
            row = t.add_row().cells
            row[0].text = x['name']
            row[1].text = str(x['count'])
            row[2].text = f'{x["count"] / total * 100:.1f}'
    else:
        doc.add_paragraph('（无数据）')

    doc.add_heading('三、事故主要原因分析', level=1)
    if cause_dist:
        t = doc.add_table(rows=1, cols=3)
        t.style = 'Light Grid Accent 1'
        hdr = t.rows[0].cells
        hdr[0].text = '事故原因'
        hdr[1].text = '数量(起)'
        hdr[2].text = '占比(%)'
        total = sum(x['count'] for x in cause_dist) or 1
        for x in cause_dist[:10]:
            row = t.add_row().cells
            row[0].text = x['name']
            row[1].text = str(x['count'])
            row[2].text = f'{x["count"] / total * 100:.1f}'
    else:
        doc.add_paragraph('（无数据）')

    doc.add_heading('四、事故多发路段 TOP10', level=1)
    if top_roads:
        t = doc.add_table(rows=1, cols=4)
        t.style = 'Light Grid Accent 1'
        hdr = t.rows[0].cells
        hdr[0].text = '排名'
        hdr[1].text = '道路名称'
        hdr[2].text = '事故数(起)'
        hdr[3].text = '死亡(人)'
        for i, x in enumerate(top_roads, 1):
            row = t.add_row().cells
            row[0].text = str(i)
            row[1].text = x['name']
            row[2].text = str(x['count'])
            row[3].text = str(x.get('deaths', 0))
    else:
        doc.add_paragraph('（无数据）')

    doc.add_heading('五、重大事故清单', level=1)
    if major_list:
        t = doc.add_table(rows=1, cols=5)
        t.style = 'Light Grid Accent 1'
        hdr = t.rows[0].cells
        hdr[0].text = '事故编号'
        hdr[1].text = '发生时间'
        hdr[2].text = '地点'
        hdr[3].text = '等级'
        hdr[4].text = '死/伤'
        for x in major_list:
            row = t.add_row().cells
            row[0].text = x['accident_no']
            row[1].text = x['occur_time']
            row[2].text = f"{x.get('road_name', '')} {x.get('road_section', '')}"
            row[3].text = x['level']
            row[4].text = f"{x['death_count']}/{x['injury_count']}"
    else:
        doc.add_paragraph('本月无重大及以上事故。')

    doc.add_heading('六、工作建议', level=1)
    suggestions = []
    if cause_dist:
        top_cause = cause_dist[0]['name']
        suggestions.append(f'本月事故主要原因为"{top_cause}"，建议加强针对性宣传教育与路面执法。')
    if top_roads:
        top_road = top_roads[0]['name']
        suggestions.append(f'"{top_road}"为事故高发路段，建议联合相关部门排查隐患、增设警示标识。')
    suggestions.append('持续推进酒驾醉驾、超速、违章变道等突出违法行为整治。')
    for s in suggestions:
        doc.add_paragraph(s, style='List Number')

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
