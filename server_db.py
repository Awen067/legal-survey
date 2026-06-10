#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业用工法律风险体检小程序 - 后端服务器（数据库版）
使用 Python 标准库 + SQLite，无需额外安装依赖
"""

import http.server
import json
import os
import re
import shutil
import sys
import sqlite3
import uuid
import zipfile
import io
from datetime import datetime
from urllib.parse import urlparse, parse_qs, quote
from pathlib import Path

# ===== 配置 =====
PORT = int(os.environ.get("PORT", 8080))

# 风险等级常量
RISK_LEVEL_5 = chr(0x2B50) * 5
RISK_LEVEL_4 = chr(0x2B50) * 4
RISK_LEVEL_3 = chr(0x2B50) * 3
RISK_LEVEL_2 = chr(0x2B50) * 2
RISK_LEVEL_1 = chr(0x2B50)

BASE_DIR = Path(__file__).parent
# Railway 持久化磁盘挂载在 /data，优先使用
HAS_VOLUME = Path("/data").exists()
DATA_DIR = BASE_DIR / "data"          # 风险库JSON始终在代码目录
DB_PATH = Path("/data/surveys.db") if HAS_VOLUME else BASE_DIR / "surveys.db"
OUTPUT_DIR = Path("/data/output") if HAS_VOLUME else BASE_DIR / "output"
TEMPLATES_DIR = BASE_DIR / "templates"

# 确保目录存在
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "docx").mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "reports").mkdir(parents=True, exist_ok=True)

# ===== 数据库初始化 =====

def init_db():
    """初始化SQLite数据库"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS surveys (
            id TEXT PRIMARY KEY,
            company_name TEXT,
            contact TEXT,
            answers TEXT,
            risk_items TEXT,
            docx_path TEXT,
            report_path TEXT,
            docx_id TEXT,
            report_id TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_surveys_created_at 
        ON surveys(created_at DESC)
    """)
    
    conn.commit()
    conn.close()
    print("[数据库] 数据库初始化完成: {}".format(DB_PATH))

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

# ===== DOCX 生成器 =====

class DocxGenerator:
    """使用原始 XML 生成 .docx 文件"""

    @staticmethod
    def _escape_xml(text):
        if not text:
            return ""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")

    @staticmethod
    def _wrap_text(text, bold=False, size=22, color="000000", font="SimSun"):
        escaped = DocxGenerator._escape_xml(text)
        b = '<w:b/>' if bold else ''
        return '<w:r><w:rPr><w:rFonts w:ascii="{}" w:hAnsi="{}" w:eastAsia="{}"/><w:sz w:val="{}"/><w:szCs w:val="{}"/><w:color w:val="{}"/>{}</w:rPr><w:t xml:space="preserve">{}</w:t></w:r>'.format(font, font, font, size, size, color, b, escaped)

    @staticmethod
    def _paragraph(text, bold=False, size=22, color="000000", alignment="left", font="SimSun", spacing_after=120, spacing_before=0, indent_left=0):
        align_map = {"left": "left", "center": "center", "right": "right", "both": "both"}
        indent = '<w:ind w:left="{}"/>'.format(indent_left) if indent_left else ""
        return '<w:p><w:pPr><w:jc w:val="{}"/><w:spacing w:after="{}" w:before="{}" w:line="360" w:lineRule="auto"/>{}</w:pPr>{}</w:p>'.format(
            align_map.get(alignment, 'left'), spacing_after, spacing_before, indent,
            DocxGenerator._wrap_text(text, bold=bold, size=size, color=color, font=font)
        )

    @staticmethod
    def generate_risk_report(submission_data):
        """生成风险报告DOCX"""
        with open(DATA_DIR / "risk_db.json", "r", encoding="utf-8") as f:
            risk_db = json.load(f)

        answers = submission_data.get("answers", {})
        company_name = submission_data.get("company_name", "未填写")
        contact = submission_data.get("contact", "未填写")
        
        risk_items = []
        for qid, user_answers in answers.items():
            qdata = risk_db.get(qid)
            if not qdata:
                continue
            question_text = qdata["question"]
            
            items_list = user_answers if isinstance(user_answers, list) else [user_answers]
            for ans in items_list:
                matched = DocxGenerator._find_option(qdata, ans)
                if matched:
                    risk_items.append({
                        "question": question_text,
                        "answer": ans,
                        "risk_point": matched["risk_point"],
                        "risk_level": matched["risk_level"],
                        "risk_analysis": matched["risk_analysis"],
                        "legal_advice": matched["legal_advice"],
                        "legal_basis": matched["legal_basis"]
                    })

        doc_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M")

        content_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        content_xml += '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        content_xml += '<w:body>'

        content_xml += DocxGenerator._paragraph("企业用工法律风险体检报告", bold=True, size=36, color="1A3C6D", alignment="center", spacing_after=60)
        content_xml += DocxGenerator._paragraph("企业名称：{}".format(company_name), size=24, color="333333", alignment="center", spacing_after=20)
        content_xml += DocxGenerator._paragraph("联系方式：{}".format(contact), size=24, color="333333", alignment="center", spacing_after=20)
        content_xml += DocxGenerator._paragraph("生成时间：{}".format(timestamp), size=22, color="666666", alignment="center", spacing_after=200)
        content_xml += DocxGenerator._paragraph("-" * 60, size=22, color="CCCCCC", alignment="center", spacing_after=200)

        total_risk = len(risk_items)
        high_risk = len([r for r in risk_items if r["risk_level"] == RISK_LEVEL_5])
        mid_risk = len([r for r in risk_items if r["risk_level"] == RISK_LEVEL_4 or r["risk_level"] == RISK_LEVEL_3])

        content_xml += DocxGenerator._paragraph("共检测到 {} 个风险项，其中高危风险 {} 项，中危风险 {} 项".format(total_risk, high_risk, mid_risk), 
                                               bold=True, size=24, color="C0392B", alignment="center", spacing_after=300)

        for idx, item in enumerate(risk_items, 1):
            content_xml += DocxGenerator._paragraph("风险项 {}：{}".format(idx, item['question']), bold=True, size=24, color="1A3C6D", spacing_before=200, spacing_after=60)
            content_xml += DocxGenerator._paragraph("您的回答：{}".format(item['answer']), size=22, color="555555", spacing_after=40)
            content_xml += DocxGenerator._paragraph("风险点：{}".format(item['risk_point']), bold=True, size=22, color="C0392B", spacing_after=40)
            content_xml += DocxGenerator._paragraph("风险等级：{}".format(item['risk_level']), size=22, color="E67E22", spacing_after=60)
            
            if item["risk_analysis"] and item["risk_analysis"] != "——":
                content_xml += DocxGenerator._paragraph("法律风险分析：", bold=True, size=22, color="333333", spacing_after=40)
                content_xml += DocxGenerator._paragraph(item["risk_analysis"], size=22, color="333333", spacing_after=60, indent_left=240)
            
            if item["legal_advice"] and item["legal_advice"] != "——":
                content_xml += DocxGenerator._paragraph("法律建议：", bold=True, size=22, color="333333", spacing_after=40)
                for line in item["legal_advice"].split("\n"):
                    if line.strip():
                        content_xml += DocxGenerator._paragraph("  • {}".format(line.strip()), size=22, color="333333", spacing_after=20, indent_left=360)
            
            if item["legal_basis"] and item["legal_basis"] != "——":
                content_xml += DocxGenerator._paragraph("法律依据：", bold=True, size=22, color="333333", spacing_after=40)
                for line in item["legal_basis"].split("\n"):
                    if line.strip():
                        content_xml += DocxGenerator._paragraph("  • {}".format(line.strip()), size=21, color="666666", spacing_after=20, indent_left=360)

            if idx < len(risk_items):
                content_xml += DocxGenerator._paragraph("- - -", size=22, color="CCCCCC", alignment="center", spacing_after=100, spacing_before=100)

        content_xml += '</w:body></w:document>'

        docx_path = str(OUTPUT_DIR / "docx" / "风险报告_{}_{}.docx".format(company_name, doc_id))
        DocxGenerator._pack_docx(content_xml, docx_path)
        
        return docx_path, doc_id, risk_items

    @staticmethod
    def _find_option(qdata, user_answer):
        """查找匹配的选项"""
        for opt in qdata.get("options", []):
            opt_text = opt["answer"]
            if user_answer == opt_text:
                return opt
            if user_answer.startswith(opt_text) or opt_text.startswith(user_answer):
                return opt
            if len(user_answer) >= 20 and len(opt_text) >= 20:
                if user_answer[:20] == opt_text[:20]:
                    return opt
        return None

    @staticmethod
    def _pack_docx(content_xml, output_path):
        """打包DOCX文件"""
        rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''

        doc_rels_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'''

        content_types_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types_xml)
            zf.writestr("_rels/.rels", rels_xml)
            zf.writestr("word/_rels/document.xml.rels", doc_rels_xml)
            zf.writestr("word/document.xml", content_xml)

    @staticmethod
    def generate_html_report(submission_data, risk_items):
        """生成HTML分析报告"""
        company_name = submission_data.get("company_name", "未填写")
        contact = submission_data.get("contact", "未填写")
        timestamp = datetime.now().strftime("%Y年%m月%d日")

        total = len(risk_items)
        high = len([r for r in risk_items if r["risk_level"] == RISK_LEVEL_5])
        mid = len([r for r in risk_items if r["risk_level"] == RISK_LEVEL_4])
        low = len([r for r in risk_items if r["risk_level"] == RISK_LEVEL_3])
        no_risk = total - high - mid - low

        risk_cards_html = ""
        for idx, item in enumerate(risk_items, 1):
            level_class = "critical" if item["risk_level"] == RISK_LEVEL_5 else ("high" if item["risk_level"] == RISK_LEVEL_4 else ("medium" if item["risk_level"] == RISK_LEVEL_3 else "low"))
            
            advice_html = ""
            if item["legal_advice"] and item["legal_advice"] != "——":
                advice_items = [l.strip() for l in item["legal_advice"].split("\n") if l.strip()]
                advice_html = "<ul>" + "".join("<li>{}</li>".format(a) for a in advice_items) + "</ul>"
            
            basis_html = ""
            if item["legal_basis"] and item["legal_basis"] != "——":
                basis_items = [l.strip() for l in item["legal_basis"].split("\n") if l.strip()]
                basis_html = "<ul>" + "".join("<li>{}</li>".format(b) for b in basis_items) + "</ul>"
            
            analysis = item["risk_analysis"] if item["risk_analysis"] and item["risk_analysis"] != "——" else ""
            
            risk_cards_html += """
            <div class="risk-card {}">
                <div class="risk-header">
                    <span class="risk-num">#{}</span>
                    <span class="risk-level-badge {}">{}</span>
                </div>
                <h3 class="risk-question">{}</h3>
                <div class="risk-answer">回复 您的回答：{}</div>
                <div class="risk-point">警告 风险点：{}</div>
                {}
                {}
                {}
            </div>""".format(
                level_class, idx, level_class, item["risk_level"],
                item["question"], item["answer"], item["risk_point"],
                '<div class="risk-analysis"><strong>法律风险分析：</strong>{}</div>'.format(analysis) if analysis else "",
                '<div class="risk-advice"><strong>法律建议：</strong>{}</div>'.format(advice_html) if advice_html else "",
                '<div class="risk-basis"><strong>法律依据：</strong>{}</div>'.format(basis_html) if basis_html else ""
            )

        report_id = str(uuid.uuid4())[:8]
        
        # 使用字符串替换避免format方法的花括号冲突
        html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>企业用工法律风险分析报告</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:#f5f7fa; color:#333; line-height:1.8; }
        .report-container { max-width:1000px; margin:0 auto; padding:20px; }
        .cover { background:linear-gradient(135deg,#1a3c6d,#2c5aa0,#3a7bd5); color:white; border-radius:16px; padding:60px 40px; text-align:center; margin-bottom:30px; box-shadow:0 10px 40px rgba(26,60,109,0.3); }
        .cover h1 { font-size:36px; font-weight:700; margin-bottom:10px; letter-spacing:4px; }
        .cover .subtitle { font-size:18px; opacity:0.85; letter-spacing:2px; }
        .cover .company-name { font-size:24px; margin-top:20px; padding:10px 40px; background:rgba(255,255,255,0.15); border-radius:30px; display:inline-block; }
        .cover .meta { margin-top:30px; font-size:14px; opacity:0.7; }
        .summary-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:30px; }
        .summary-card { background:white; border-radius:12px; padding:24px 20px; text-align:center; box-shadow:0 2px 12px rgba(0,0,0,0.06); border-top:4px solid; }
        .summary-card .num { font-size:42px; font-weight:700; margin-bottom:6px; }
        .summary-card .label { font-size:14px; color:#888; }
        .summary-card.total { border-color:#1a3c6d; }
        .summary-card.total .num { color:#1a3c6d; }
        .summary-card.critical { border-color:#e74c3c; }
        .summary-card.critical .num { color:#e74c3c; }
        .summary-card.high { border-color:#e67e22; }
        .summary-card.high .num { color:#e67e22; }
        .summary-card.medium { border-color:#f39c12; }
        .summary-card.medium .num { color:#f39c12; }
        .chart-section { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:30px; }
        .chart-box { background:white; border-radius:12px; padding:24px; box-shadow:0 2px 12px rgba(0,0,0,0.06); }
        .chart-box h3 { font-size:16px; color:#1a3c6d; margin-bottom:16px; text-align:center; }
        .chart-box canvas { max-height:280px; }
        .section-title { font-size:22px; color:#1a3c6d; margin:30px 0 20px; padding-left:16px; border-left:4px solid #1a3c6d; font-weight:700; }
        .risk-card { background:white; border-radius:10px; padding:24px; margin-bottom:16px; box-shadow:0 2px 8px rgba(0,0,0,0.05); border-left:5px solid; }
        .risk-card.critical { border-left-color:#e74c3c; }
        .risk-card.high { border-left-color:#e67e22; }
        .risk-card.medium { border-left-color:#f39c12; }
        .risk-card.low { border-left-color:#27ae60; }
        .risk-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
        .risk-num { font-size:14px; color:#999; font-weight:600; }
        .risk-level-badge { padding:4px 14px; border-radius:20px; font-size:13px; font-weight:600; color:white; }
        .risk-level-badge.critical { background:#e74c3c; }
        .risk-level-badge.high { background:#e67e22; }
        .risk-level-badge.medium { background:#f39c12; }
        .risk-level-badge.low { background:#27ae60; }
        .risk-question { font-size:17px; font-weight:600; color:#1a3c6d; margin-bottom:12px; }
        .risk-answer { font-size:14px; color:#666; margin-bottom:8px; padding:8px 12px; background:#f8f9fa; border-radius:6px; }
        .risk-point { font-size:15px; color:#e74c3c; font-weight:600; margin-bottom:12px; }
        .risk-analysis, .risk-advice, .risk-basis { font-size:14px; color:#555; margin-bottom:10px; line-height:1.8; }
        .risk-analysis strong, .risk-advice strong, .risk-basis strong { color:#1a3c6d; }
        .risk-card ul { padding-left:20px; }
        .risk-card li { margin-bottom:4px; }
        .footer { text-align:center; padding:40px 20px; color:#aaa; font-size:13px; border-top:1px solid #eee; margin-top:40px; }
        @media(max-width:768px){ .summary-grid { grid-template-columns:repeat(2,1fr); } .chart-section { grid-template-columns:1fr; } .cover h1 { font-size:24px; } }
    </style>
</head>
<body>
    <div class="report-container">
        <div class="cover">
            <div style="font-size:64px;margin-bottom:20px;">⚖️</div>
            <h1>企业用工法律风险分析报告</h1>
            <div class="subtitle">Employment Legal Risk Analysis Report</div>
            <div class="company-name">__COMPANY_NAME__</div>
            <div class="meta">报告生成时间：__TIMESTAMP__ ｜ 法律体检专用</div>
        </div>
        <div class="summary-grid">
            <div class="summary-card total"><div class="num">__TOTAL__</div><div class="label">风险项总数</div></div>
            <div class="summary-card critical"><div class="num">__HIGH__</div><div class="label">🔴 高危风险</div></div>
            <div class="summary-card high"><div class="num">__MID__</div><div class="label">🟠 中高风险</div></div>
            <div class="summary-card medium"><div class="num">__LOW__</div><div class="label">🟡 一般风险</div></div>
        </div>
        <div class="chart-section">
            <div class="chart-box"><h3>📊 风险等级分布</h3><canvas id="riskPieChart"></canvas></div>
            <div class="chart-box"><h3>📈 风险评估概览</h3><canvas id="riskBarChart"></canvas></div>
        </div>
        <h2 class="section-title">📋 风险详情分析</h2>
        __RISK_CARDS__
        <div class="footer">
            <p>本报告基于《企业用工合规项目法律风险查询库》自动生成</p>
            <p>仅供参考，不构成正式法律意见。如有疑问，请咨询专业律师</p>
            <p>© __YEAR__ 企业用工法律风险体检小程序</p>
        </div>
    </div>
    <script>
        new Chart(document.getElementById('riskPieChart'), {
            type:'doughnut',
            data:{labels:['高危','中高','中等','其他'],datasets:[{data:[__HIGH__,__MID__,__LOW__,__NO_RISK__],backgroundColor:['#e74c3c','#e67e22','#f39c12','#95a5a6'],borderWidth:2,borderColor:'#fff'}]},
            options:{responsive:true,plugins:{legend:{position:'bottom'}}}
        });
        new Chart(document.getElementById('riskBarChart'), {
            type:'bar',
            data:{labels:['高危','中高','中等','其他'],datasets:[{label:'风险项数量',data:[__HIGH__,__MID__,__LOW__,__NO_RISK__],backgroundColor:['#e74c3c','#e67e22','#f39c12','#95a5a6'],borderRadius:8}]},
            options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}
        });
    </script>
</body>
</html>"""
        
        html = html.replace("__COMPANY_NAME__", company_name)
        html = html.replace("__TIMESTAMP__", timestamp)
        html = html.replace("__TOTAL__", str(total))
        html = html.replace("__HIGH__", str(high))
        html = html.replace("__MID__", str(mid))
        html = html.replace("__LOW__", str(low))
        html = html.replace("__NO_RISK__", str(no_risk))
        html = html.replace("__RISK_CARDS__", risk_cards_html)
        html = html.replace("__YEAR__", str(datetime.now().year))

        report_path = str(OUTPUT_DIR / "reports" / "分析报告_{}_{}.html".format(company_name, report_id))
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        
        return report_path, report_id

# ===== HTTP 请求处理器 =====

class SurveyHandler(http.server.SimpleHTTPRequestHandler):
    """处理所有 HTTP 请求"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/survey":
            self.serve_file("templates/survey.html", "text/html; charset=utf-8")
        elif path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        elif path == "/admin":
            self.serve_admin()
        elif path.startswith("/data/"):
            self.serve_data_file(path)
        elif path == "/api/submissions":
            self.serve_submissions_list()
        elif path.startswith("/api/download/docx/"):
            self.serve_download(path.replace("/api/download/docx/", ""), "docx")
        elif path.startswith("/api/download/report/"):
            self.serve_download(path.replace("/api/download/report/", ""), "report")
        elif path.startswith("/api/report/"):
            report_id = path.replace("/api/report/", "")
            self.serve_report_view(report_id)
        elif path == "/api/db/backup":
            self.serve_db_backup()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/submit":
            self.handle_submit()
        elif path == "/api/db/restore":
            self.handle_db_restore()
        else:
            self.send_error(404)

    def serve_file(self, rel_path, content_type):
        filepath = BASE_DIR / rel_path
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(content.encode("utf-8")))
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        else:
            self.send_error(404)

    def serve_data_file(self, path):
        rel_path = path[len("/data/"):]
        filepath = DATA_DIR / rel_path
        if ".." in rel_path or not filepath.exists():
            self.send_error(404)
            return
        with open(filepath, "rb") as f:
            content = f.read()
        ct = "application/json; charset=utf-8" if filepath.suffix == ".json" else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", len(content))
        self.end_headers()
        self.wfile.write(content)

    def handle_submit(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        company_name = data.get("company_name", "未填写")
        submission_id = str(uuid.uuid4())[:8]
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        doc_id = ""
        report_id = ""
        docx_path = ""
        report_path = ""
        risk_items = []
        
        try:
            docx_path, doc_id, risk_items = DocxGenerator.generate_risk_report(data)
        except Exception as e:
            print("[错误] DOCX生成失败: {}".format(e))
            import traceback
            traceback.print_exc()
            
        try:
            report_path, report_id = DocxGenerator.generate_html_report(data, risk_items)
        except Exception as e:
            print("[错误] HTML报告生成失败: {}".format(e))
            import traceback
            traceback.print_exc()
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO surveys (id, company_name, contact, answers, risk_items, docx_path, report_path, docx_id, report_id, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    submission_id,
                    company_name,
                    data.get("contact", ""),
                    json.dumps(data.get("answers", {}), ensure_ascii=False),
                    json.dumps(risk_items, ensure_ascii=False),
                    docx_path,
                    report_path,
                    doc_id,
                    report_id,
                    created_at,
                    "processed"
                )
            )
            conn.commit()
            conn.close()
            print("[数据库] 保存提交记录: {} - {}".format(submission_id, company_name))
        except Exception as e:
            print("[数据库] 保存失败: {}".format(e))
            import traceback
            traceback.print_exc()

        response = {
            "success": True,
            "submission_id": submission_id,
            "docx_id": doc_id,
            "report_id": report_id,
            "message": "感谢您的参与！后续会有律师专门为您进行专业解析，敬请期待！"
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))

    def serve_admin(self):
        """管理员后台页面"""
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>管理员后台 - 企业用工法律风险体检</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:#f5f7fa; color:#333; min-height:100vh; }
        .header { background:linear-gradient(135deg,#1a3c6d,#2c5aa0); color:white; padding:20px 40px; display:flex; justify-content:space-between; align-items:center; }
        .header h1 { font-size:22px; font-weight:600; }
        .header .badge { background:rgba(255,255,255,0.2); padding:6px 16px; border-radius:20px; font-size:13px; }
        .container { max-width:1200px; margin:30px auto; padding:0 20px; }
        .toolbar { display:flex; gap:12px; margin-bottom:20px; }
        .btn { display:inline-block; padding:10px 20px; border-radius:6px; text-decoration:none; font-size:14px; font-weight:600; border:none; cursor:pointer; }
        .btn-primary { background:#1a3c6d; color:white; }
        .btn-success { background:#27ae60; color:white; }
        .btn-warning { background:#e67e22; color:white; }
        .btn-danger { background:#e74c3c; color:white; }
        table { width:100%; border-collapse:collapse; background:white; border-radius:10px; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,0.06); }
        th { background:#f0f4f8; color:#1a3c6d; font-weight:600; padding:14px 16px; text-align:left; font-size:14px; }
        td { padding:14px 16px; border-bottom:1px solid #f0f0f0; font-size:14px; }
        tr:hover { background:#fafbfc; }
        .actions { display:flex; gap:6px; }
        .empty { text-align:center; padding:60px; color:#999; }
        .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:30px; }
        .stat-card { background:white; padding:20px; border-radius:10px; box-shadow:0 2px 12px rgba(0,0,0,0.06); text-align:center; }
        .stat-card .num { font-size:36px; font-weight:700; color:#1a3c6d; }
        .stat-card .label { font-size:14px; color:#666; margin-top:4px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>平衡 管理员后台 - 企业用工法律风险体检</h1>
        <div class="badge">锁定 仅限管理员访问</div>
    </div>
    <div class="container">
        <div class="stats" id="stats"></div>
        <div class="toolbar">
            <button class="btn btn-success" onclick="backupDB()">下载 备份数据库</button>
            <button class="btn btn-warning" onclick="document.getElementById('restoreFile').click()">上传 恢复数据库</button>
            <input type="file" id="restoreFile" style="display:none" accept=".db" onchange="restoreDB(this)">
        </div>
        <h2 class="section-title">问卷提交记录</h2>
        <div id="submissionsTable"></div>
    </div>
    <script>
        let allSubmissions = [];
        
        async function loadSubmissions() {
            try {
                const resp = await fetch('/api/submissions');
                const data = await resp.json();
                allSubmissions = data;
                const div = document.getElementById('submissionsTable');
                if (data.length === 0) {
                    div.innerHTML = '<div class="empty"><div style="font-size:48px;margin-bottom:16px;">📭</div><p>暂无提交记录</p></div>';
                    updateStats(data);
                    return;
                }
                updateStats(data);
                let html = '<table><thead><tr><th>提交时间</th><th>企业名称</th><th>联系方式</th><th>风险项</th><th>操作</th></tr></thead><tbody>';
                for (const s of data) {
                    const riskCount = s.risk_items ? s.risk_items.length : 0;
                    let actions = '';
                    if (s.docx_id) actions += '<a class="btn btn-primary" href="/api/download/docx/' + s.docx_id + '" download>📄 下载DOCX</a>';
                    if (s.report_id) actions += '<a class="btn btn-success" href="/api/report/' + s.report_id + '" target="_blank">📊 查看报告</a>';
                    html += '<tr><td>' + s.created_at + '</td><td>' + s.company_name + '</td><td>' + s.contact + '</td><td>' + riskCount + '项</td><td class="actions">' + (actions || '—') + '</td></tr>';
                }
                html += '</tbody></table>';
                div.innerHTML = html;
            } catch(e) {
                document.getElementById('submissionsTable').innerHTML = '<div class="empty"><p>加载失败，请刷新页面</p></div>';
            }
        }
        
        function updateStats(data) {
            const total = data.length;
            const today = new Date().toISOString().split('T')[0];
            const todayCount = data.filter(s => s.created_at && s.created_at.startsWith(today)).length;
            const totalRisk = data.reduce((sum, s) => sum + (s.risk_items ? s.risk_items.length : 0), 0);
            const avgRisk = total > 0 ? (totalRisk / total).toFixed(1) : 0;
            
            document.getElementById('stats').innerHTML = 
                '<div class="stat-card"><div class="num">' + total + '</div><div class="label">总提交数</div></div>' +
                '<div class="stat-card"><div class="num">' + todayCount + '</div><div class="label">今日提交</div></div>' +
                '<div class="stat-card"><div class="num">' + totalRisk + '</div><div class="label">总风险项</div></div>' +
                '<div class="stat-card"><div class="num">' + avgRisk + '</div><div class="label">平均风险项/企业</div></div>';
        }
        
        function backupDB() {
            window.location.href = '/api/db/backup';
        }
        
        async function restoreDB(fileInput) {
            const file = fileInput.files[0];
            if (!file) return;
            
            if (!confirm('确定要恢复数据库吗？当前数据将被覆盖！')) {
                fileInput.value = '';
                return;
            }
            
            const formData = new FormData();
            formData.append('dbfile', file);
            
            try {
                const resp = await fetch('/api/db/restore', {
                    method: 'POST',
                    body: formData
                });
                const result = await resp.json();
                if (result.success) {
                    alert('数据库恢复成功！');
                    location.reload();
                } else {
                    alert('恢复失败：' + result.message);
                }
            } catch(e) {
                alert('恢复失败：' + e.message);
            }
            fileInput.value = '';
        }
        
        loadSubmissions();
    </script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(html.encode("utf-8")))
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def serve_submissions_list(self):
        """返回所有提交记录（从数据库）"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM surveys ORDER BY created_at DESC')
            rows = cursor.fetchall()
            conn.close()
            
            submissions = []
            for row in rows:
                submissions.append({
                    "id": row["id"],
                    "company_name": row["company_name"],
                    "contact": row["contact"],
                    "created_at": row["created_at"],
                    "docx_id": row["docx_id"],
                    "report_id": row["report_id"],
                    "status": row["status"],
                    "risk_items": json.loads(row["risk_items"]) if row["risk_items"] else []
                })
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(submissions, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            print("[API] 获取提交列表失败: {}".format(e))
            self.send_error(500, str(e))

    def serve_download(self, file_id, file_type):
        """下载文件"""
        if file_type == "docx":
            search_dir = OUTPUT_DIR / "docx"
            pattern = "*{}*".format(file_id)
        else:
            search_dir = OUTPUT_DIR / "reports"
            pattern = "*{}*".format(file_id)
        
        files = list(search_dir.glob(pattern))
        if not files:
            self.send_error(404, "File not found")
            return
        
        filepath = files[0]
        with open(filepath, "rb") as f:
            content = f.read()
        
        if file_type == "docx":
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename_cn = "企业用工法律风险报告_{}.docx".format(file_id)
            filename_en = "legal_risk_report_{}.docx".format(file_id)
        else:
            content_type = "text/html; charset=utf-8"
            filename_cn = "法律分析报告_{}.html".format(file_id)
            filename_en = "legal_analysis_report_{}.html".format(file_id)
        
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", 
            "attachment; filename=\"{}\"; filename*=UTF-8''{}".format(filename_en, quote(filename_cn)))
        self.send_header("Content-Length", len(content))
        self.end_headers()
        self.wfile.write(content)

    def serve_report_view(self, report_id):
        """在浏览器中查看报告"""
        search_dir = OUTPUT_DIR / "reports"
        files = list(search_dir.glob("*{}*".format(report_id)))
        if not files:
            self.send_error(404, "Report not found")
            return
        
        with open(files[0], "r", encoding="utf-8") as f:
            html = f.read()
        
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(html.encode("utf-8")))
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def serve_db_backup(self):
        """备份数据库"""
        try:
            import gc
            gc.collect()
            
            backup_path = OUTPUT_DIR / "backup_{}.db".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
            shutil.copy2(str(DB_PATH), str(backup_path))
            
            with open(backup_path, "rb") as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 
                "attachment; filename=\"surveys_backup_{}.db\"".format(datetime.now().strftime("%Y%m%d_%H%M%S")))
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
            
            backup_path.unlink()
        except Exception as e:
            print("[备份] 失败: {}".format(e))
            self.send_error(500, str(e))

    def handle_db_restore(self):
        """恢复数据库"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            
            temp_db_path = OUTPUT_DIR / "temp_restore.db"
            with open(temp_db_path, "wb") as f:
                f.write(body)
            
            try:
                test_conn = sqlite3.connect(str(temp_db_path))
                test_cursor = test_conn.cursor()
                test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='surveys'")
                result = test_cursor.fetchone()
                test_conn.close()
                
                if not result:
                    raise Exception("无效的数据库文件：缺少surveys表")
            except Exception as e:
                temp_db_path.unlink()
                self.send_error(400, "无效的数据库文件: {}".format(e))
                return
            
            import gc
            gc.collect()
            
            backup_path = DB_PATH.with_suffix('.db.bak')
            if DB_PATH.exists():
                shutil.copy2(str(DB_PATH), str(backup_path))
            
            shutil.move(str(temp_db_path), str(DB_PATH))
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "message": "数据库恢复成功"}).encode("utf-8"))
        except Exception as e:
            print("[恢复] 失败: {}".format(e))
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def log_message(self, format, *args):
        print("[{}] {}".format(datetime.now().strftime('%H:%M:%S'), args[0] if args else ''))

def main():
    init_db()
    
    print("=" * 60)
    print("   企业用工法律风险体检小程序（数据库版）")
    print("=" * 60)
    print("   服务器启动成功！")
    print("   问卷地址：http://localhost:{}".format(PORT))
    print("   管理后台：http://localhost:{}/admin".format(PORT))
    print("   数据库：{}".format(DB_PATH))
    print("   按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    server = http.server.HTTPServer(("0.0.0.0", PORT), SurveyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        server.shutdown()

if __name__ == "__main__":
    main()
