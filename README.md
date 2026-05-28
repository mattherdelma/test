# 道路交通事故统计与可视化分析系统

单机版（Windows 10）/ Python + Flask + SQLite + ECharts 实现的本地浏览器应用。
面向交警业务部门：事故信息录入、台账查询、多维统计、可视化大屏、Word 月报导出。

## 一、快速开始（Windows 10）

1. 安装 Python 3.9+（[官网下载](https://www.python.org/downloads/)，安装时勾选 **Add to PATH**）
2. 双击项目根目录下的 **run.bat**
   - 首次运行会自动：下载 ECharts、安装依赖、初始化数据库、生成约 1500 条演示数据
   - 之后启动只需双击该脚本，浏览器会自动打开 `http://127.0.0.1:5000`
3. 登录账号
   - `admin / admin123` — 管理员（全部权限）
   - `recorder / 123456` — 录入员（录入、修改）
   - `viewer / 123456` — 查看者（只读，给领导用）

## 二、功能模块

| 模块 | 说明 |
|---|---|
| 数据驾驶舱 | KPI 卡 + 9 张图表（趋势、类型、原因、TOP路段、时段热力图、辖区分布等） |
| 事故台账 | 列表 + 多条件筛选 + 详情 + Excel 导出 |
| 事故录入 | 表单录入，下拉字典减少错填，支持多辆车 / 多人员 |
| 统计分析 | 可切换维度的交叉分析（类型 / 等级 / 原因 / 天气 / 道路 / 路面 / 辖区） |
| 字典维护 | 13 类下拉项可在线增加（路段、类型、原因等） |
| 用户与日志 | 用户管理、操作日志、数据备份 |
| 报表导出 | 一键导出 Word 月报（含同比、TOP路段、原因分析、重大事故清单、工作建议） |

## 三、目录结构

```
.
├─ app.py                  Flask 主程序（含全部路由和 API）
├─ database.py             数据库初始化与连接
├─ seed_data.py            演示数据生成（3 年共约 1500 条）
├─ report_generator.py     Excel / Word 报表生成
├─ download_libs.py        前端依赖（ECharts）下载脚本
├─ run.bat                 Windows 一键启动
├─ requirements.txt
├─ static/
│  ├─ css/style.css
│  └─ js/{echarts.min.js, common.js}
├─ templates/              页面模板
├─ data/accidents.db       SQLite 数据库
├─ backup/                 自动备份（保留 30 天）
└─ uploads/                附件目录（预留）
```

## 四、数据库表

- `users` 用户（id / 用户名 / 密码哈希 / 角色 / 姓名）
- `accidents` 事故主表（25 个字段，含时间、地点、伤亡、原因等）
- `vehicles` 涉事车辆（一对多）
- `persons` 涉事人员（一对多）
- `dictionaries` 字典（13 类下拉项）
- `operation_logs` 操作日志

关键字段加了索引：`occur_time / district / level / type / road_name`，10 万级数据查询无压力。

## 五、给领导演示的几个亮点

1. **数据驾驶舱**首屏 4 个 KPI 卡（事故 / 死亡 / 受伤 / 损失）+ 同比涨跌
2. **月度趋势图**自带涨跌势对比，支持切换 3/6/12/24/36 个月
3. **时段热力图**直观展示事故高发时段
4. **TOP 路段排行**自动定位事故多发点
5. **Word 月报**一键生成，含同比分析、TOP 排名、重大事故清单、工作建议——可直接打印呈报

## 六、打包成 EXE（可选）

如需脱离 Python 环境分发：

```bash
pip install pyinstaller
pyinstaller -F -w --add-data "templates;templates" --add-data "static;static" --add-data "data;data" --hidden-import openpyxl --hidden-import docx app.py
```

生成的 `dist/app.exe` 可直接拷贝运行（首次仍会创建 `data/` 数据库）。

## 七、常见问题

**Q: 如何重置全部数据 / 重新生成演示数据？**
A: 关闭程序，删除 `data/accidents.db`，重新启动即可。

**Q: 如何完全离线（无网络）部署？**
A: 在有网机器上完成首次 `run.bat`（已下载 ECharts、安装依赖），把整个目录连同 Python 安装一起拷贝到目标机器。或者使用「打包成 EXE」方式。

**Q: 数据备份位置？**
A: 启动时自动备份到 `backup/auto_yyyymmdd.db`，保留 30 天；管理员可在「用户与日志」页手动备份。

**Q: 默认密码必须改？**
A: 是。管理员登录后到「用户与日志」页重置 admin 密码，并删除不需要的演示账号。
