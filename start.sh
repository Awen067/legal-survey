#!/bin/bash
# ============================================
#   企业用工法律风险体检小程序 - 启动脚本
#   无需安装任何依赖，使用系统自带 Python3
# ============================================

cd "$(dirname "$0")"

echo "============================================"
echo "  ⚖️  企业用工法律风险体检小程序"
echo "  请选择启动版本："
echo "============================================"
echo ""
echo "  1) 标准版 (文件系统存储)"
echo "  2) 数据库版 (SQLite存储) [推荐]"
echo "  3) 退出"
echo ""
read -p "  请选择 (1/2/3): " choice

if [ "$choice" = "1" ]; then
    SERVER_FILE="server.py"
    echo ""
    echo "  已选择：标准版 (文件系统存储)"
elif [ "$choice" = "2" ]; then
    SERVER_FILE="server_db.py"
    echo ""
    echo "  已选择：数据库版 (SQLite存储)"
elif [ "$choice" = "3" ]; then
    echo "  已取消启动"
    exit 0
else
    echo "  无效选择，默认使用数据库版"
    SERVER_FILE="server_db.py"
fi

echo ""
echo "============================================"
echo "  ⚖️  企业用工法律风险体检小程序"
echo "  正在启动服务器..."
echo "============================================"

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误：未找到 Python3，请先安装 Python3"
    echo "   下载地址：https://www.python.org/downloads/"
    exit 1
fi

echo "   Python 版本: $(python3 --version)"
echo ""
echo "   服务器即将启动，请打开浏览器访问："
echo ""
echo "   📋 问卷页面：http://localhost:8080"
echo "   🔒 管理后台：http://localhost:8080/admin"
echo ""
echo "   按 Ctrl+C 停止服务器"
echo "============================================"

python3 $SERVER_FILE
