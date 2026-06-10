#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据迁移脚本：从文件系统迁移到SQLite数据库
将 output/submissions/ 目录下的JSON文件导入 surveys.db
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "surveys.db"
SUBMISSIONS_DIR = BASE_DIR / "output" / "submissions"

def init_db():
    """初始化数据库（如果不存在）"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute('''
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
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_surveys_created_at 
        ON surveys(created_at DESC)
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ 数据库初始化完成: {DB_PATH}")

def migrate_submissions():
    """迁移提交记录"""
    if not SUBMISSIONS_DIR.exists():
        print(f"❌ 提交目录不存在: {SUBMISSIONS_DIR}")
        return
    
    json_files = list(SUBMISSIONS_DIR.glob("*.json"))
    if not json_files:
        print(f"ℹ️  没有找到提交记录文件")
        return
    
    print(f"📋 找到 {len(json_files)} 个提交记录文件")
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    migrated_count = 0
    skipped_count = 0
    
    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            submission_id = json_file.stem  # 文件名（不含扩展名）
            
            # 检查是否已存在
            cursor.execute("SELECT id FROM surveys WHERE id = ?", (submission_id,))
            if cursor.fetchone():
                print(f"⏭️  跳过（已存在）: {submission_id}")
                skipped_count += 1
                continue
            
            # 提取数据
            company_name = data.get("company_name", "未填写")
            contact = data.get("contact", "未填写")
            answers = json.dumps(data.get("answers", {}), ensure_ascii=False)
            
            # 风险项（从数据中提取或留空）
            risk_items = json.dumps(data.get("risk_items", []), ensure_ascii=False)
            
            # 文件路径
            docx_path = data.get("_docx_path", "")
            report_path = data.get("_report_path", "")
            docx_id = data.get("_docx_id", "")
            report_id = data.get("_report_id", "")
            
            # 创建时间（使用文件修改时间）
            created_at = datetime.fromtimestamp(json_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            # 插入数据库
            cursor.execute('''
                INSERT INTO surveys (id, company_name, contact, answers, risk_items, docx_path, report_path, docx_id, report_id, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                submission_id,
                company_name,
                contact,
                answers,
                risk_items,
                docx_path,
                report_path,
                docx_id,
                report_id,
                created_at,
                "migrated"
            ))
            
            print(f"✅ 已迁移: {submission_id} - {company_name}")
            migrated_count += 1
            
        except Exception as e:
            print(f"❌ 迁移失败: {json_file.name} - {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n📊 迁移完成:")
    print(f"   ✅ 成功: {migrated_count} 条")
    print(f"   ⏭️  跳过: {skipped_count} 条")
    print(f"   📁 总计: {len(json_files)} 条")

def main():
    print("=" * 60)
    print("  📂➡️💾 数据迁移：文件系统 → SQLite数据库")
    print("=" * 60)
    print()
    
    # 1. 初始化数据库
    init_db()
    
    # 2. 迁移数据
    migrate_submissions()
    
    print()
    print("=" * 60)
    print("  ✅ 迁移完成！")
    print("  现在可以使用数据库版服务器了：")
    print("  python3 server_db.py")
    print("=" * 60)

if __name__ == "__main__":
    main()
