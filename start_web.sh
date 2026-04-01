#!/bin/bash
# 启动期货交易建议Web应用

echo "🚀 启动期货交易建议系统..."
echo "📊 访问地址: http://localhost:8501"
echo "⏹️  按 Ctrl+C 停止服务"
echo ""

streamlit run web_app.py --server.port 8501 --server.address localhost
