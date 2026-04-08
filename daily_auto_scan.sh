#!/bin/bash
# 每日自动更新和扫描脚本

echo "=========================================="
echo "期货市场每日自动扫描"
echo "=========================================="

# 获取当前日期
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)

echo ""
echo "扫描日期: $TODAY"
echo ""

# 1. 更新价格数据
echo "步骤1: 更新价格数据..."
python3 daily_scanner.py --date $YESTERDAY --update --threshold 0.05
python3 daily_scanner.py --date $TODAY --update --threshold 0.05

# 2. 确定展示哪天的结果（优先今天，否则昨天）
if [ -f "daily_scan_output/scan_${TODAY}.csv" ]; then
    DISPLAY_DATE=$TODAY
else
    DISPLAY_DATE=$YESTERDAY
fi

echo ""
echo "=========================================="
echo "扫描完成！展示日期: $DISPLAY_DATE"
echo "=========================================="
echo ""
echo "结果文件:"
echo "  - daily_scan_output/scan_${DISPLAY_DATE}.csv (完整数据)"
echo "  - daily_scan_output/bullish_${DISPLAY_DATE}.csv (偏多品种)"
echo "  - daily_scan_output/bearish_${DISPLAY_DATE}.csv (偏空品种)"
echo ""

# 3. 显示偏多和偏空品种数量
if [ -f "daily_scan_output/bullish_${DISPLAY_DATE}.csv" ]; then
    BULLISH_COUNT=$(wc -l < "daily_scan_output/bullish_${DISPLAY_DATE}.csv")
    BULLISH_COUNT=$((BULLISH_COUNT - 1))  # 减去表头
    echo "偏多品种: $BULLISH_COUNT 个"
fi

if [ -f "daily_scan_output/bearish_${DISPLAY_DATE}.csv" ]; then
    BEARISH_COUNT=$(wc -l < "daily_scan_output/bearish_${DISPLAY_DATE}.csv")
    BEARISH_COUNT=$((BEARISH_COUNT - 1))  # 减去表头
    echo "偏空品种: $BEARISH_COUNT 个"
fi

echo ""
echo "提示: 可以使用以下命令查看详细信息:"
echo "  cat daily_scan_output/bullish_${DISPLAY_DATE}.csv"
echo "  cat daily_scan_output/bearish_${DISPLAY_DATE}.csv"
