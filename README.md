# 期货交易建议系统

## 核心文件说明

### 数据获取模块
- `features_position.py` - 持仓数据获取（从东方财富网）
- `price_fetcher.py` - 价格数据获取

### 分析模块
- `daily_scanner.py` - 每日市场情绪扫描，生成做多/做空品种列表
- `generate_recommendations.py` - 生成交易建议（命令行版本）
- `strategy_runner.py` - 回测策略（可选）

### Web界面
- `web_app.py` - Streamlit Web应用
- `start_web.sh` - 启动Web应用的脚本

### 自动化脚本
- `daily_auto_scan.sh` - 每日自动扫描脚本（可配置定时任务）

## 使用方法

### 1. 每日扫描
```bash
python daily_scanner.py
```

### 2. 查看交易建议（命令行）
```bash
python generate_recommendations.py
```

### 3. 启动Web界面（推荐）
```bash
./start_web.sh
```
然后访问 http://localhost:8501

### 4. 设置自动扫描（可选）
编辑 crontab：
```bash
crontab -e
```
添加：
```
0 16 * * 1-5 cd /home/qiyun/project/qihuo && ./daily_auto_scan.sh
```

## 数据说明

- 净持仓比例：前20大席位的多空净持仓占比
- 60日均值：过去60个交易日的净持仓比例平均值
- 情绪变化：加强↑ / 稳定→ / 减弱↓
- 建议：优先关注情绪加强的品种
# qihuo
