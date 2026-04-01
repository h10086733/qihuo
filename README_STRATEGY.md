# 期货大户跟单策略系统

## 功能概述

本系统实现了完整的期货大户跟单策略，包括：

1. **价格数据获取** - 获取期货每日开盘价、收盘价、最高价、最低价
2. **持仓数据获取** - 下载持仓大户席位数据
3. **策略执行** - 根据大户加多/加空进行跟单交易

## 文件说明

- `price_fetcher.py` - 价格数据获取模块（新增）
- `strategy_runner.py` - 策略执行器（新增）
- `features_position.py` - 持仓数据获取模块（已有）
- `big_trader_follow.py` - 大户跟单策略（已有）
- `timing_optimize.py` - 择时优化模块（已有）

## 快速开始

### 1. 测试价格数据获取

```bash
# 获取IF主力连续合约的价格数据
python price_fetcher.py --symbol IF0 --start 2025-01-01 --end 2025-03-31

# 获取具体合约的价格数据
python price_fetcher.py --symbol IF2504 --start 2025-01-01 --end 2025-03-31

# 强制刷新数据
python price_fetcher.py --symbol IF0 --start 2025-01-01 --refresh
```

### 2. 运行完整策略

```bash
# 基础用法：跟踪IF品种前20大席位
python strategy_runner.py --variety IF --start 2025-01-01 --end 2025-03-31

# 自定义参数
python strategy_runner.py \
    --variety IF \
    --start 2025-01-01 \
    --end 2025-03-31 \
    --top-n 10 \
    --lookback 3 \
    --threshold 0.03

# 强制刷新所有数据
python strategy_runner.py --variety IF --refresh
```

### 3. 使用已有的大户跟单策略

```bash
# 单品种回测
python big_trader_follow.py \
    --start 2025-01-01 \
    --end 2025-03-31 \
    --varieties IF \
    --top-k 5 \
    --lookback 3 \
    --threshold 0.03

# 多品种回测
python big_trader_follow.py \
    --start 2025-01-01 \
    --varieties IF,I,RB \
    --scan

# 参数扫描（寻找最优参数）
python big_trader_follow.py \
    --start 2025-01-01 \
    --varieties IF \
    --scan \
    --top-k-list "3,5,8,10" \
    --lookback-list "1,3,5" \
    --threshold-list "0.0,0.03,0.05"
```

## 策略逻辑

### 持仓数据获取

1. 从东方财富网获取每日前20大席位的持仓数据
2. 计算多头总持仓和空头总持仓
3. 计算净持仓 = 多头总持仓 - 空头总持仓
4. 计算净持仓比例 = 净持仓 / (多头总持仓 + 空头总持仓)

### 信号生成

**做多信号**：
- 净持仓比例 > 阈值
- 净持仓相比N天前增加

**做空信号**：
- 净持仓比例 < -阈值
- 净持仓相比N天前减少

**空仓**：
- 其他情况

### 交易执行

- 信号产生当日不交易
- 次日开盘价开仓
- 当日收盘价计算收益

## 参数说明

### price_fetcher.py

- `--symbol`: 期货代码（如 IF0 表示主力连续，IF2504 表示具体合约）
- `--start`: 开始日期（YYYY-MM-DD）
- `--end`: 结束日期（YYYY-MM-DD）
- `--refresh`: 强制刷新数据（忽略缓存）
- `--db`: 数据库路径（默认：futures_position.db）

### strategy_runner.py

- `--variety`: 品种代码（如 IF, I, RB）
- `--start`: 开始日期
- `--end`: 结束日期
- `--top-n`: 跟踪前N大席位（默认：20）
- `--lookback`: 回看天数（默认：1）
- `--threshold`: 净持仓比例阈值（默认：0.0）
- `--refresh`: 强制刷新数据
- `--db`: 数据库路径

### big_trader_follow.py

- `--varieties`: 品种列表（逗号分隔，如 IF,I,RB）
- `--top-k`: 跟踪前K大席位（默认：5）
- `--lookback`: 回看天数（默认：3）
- `--threshold`: 净持仓比例阈值（默认：0.03）
- `--scan`: 执行参数扫描
- `--objective`: 优化目标（annual_return, sharpe, win_rate）

## 输出文件

### 价格数据

- `{symbol}_prices.csv` - 价格数据CSV文件

### 策略结果

- `strategy_output/{variety}_top{n}_lb{lookback}_th{threshold}_result.csv` - 详细回测结果
- `big_trader_output/{variety}_member_snapshot.csv` - 席位快照
- `big_trader_output/{variety}_scan.csv` - 参数扫描结果
- `big_trader_output/{variety}_best.csv` - 最优参数
- `big_trader_output/all_varieties_summary.csv` - 多品种汇总

## 数据库结构

### daily_prices 表

```sql
CREATE TABLE daily_prices (
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, symbol)
)
```

### contract_cache 表

```sql
CREATE TABLE contract_cache (
    trade_date TEXT NOT NULL,
    variety TEXT NOT NULL,
    status TEXT NOT NULL,
    contracts_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, variety)
)
```

### position_cache 表

```sql
CREATE TABLE position_cache (
    trade_date TEXT NOT NULL,
    contract TEXT NOT NULL,
    rank_field TEXT NOT NULL,
    status TEXT NOT NULL,
    rows_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, contract, rank_field)
)
```

## 常见品种代码

- **股指期货**: IF (沪深300), IC (中证500), IH (上证50), IM (中证1000)
- **商品期货**:
  - 黑色系: RB (螺纹钢), I (铁矿石), J (焦炭), JM (焦煤)
  - 化工: TA (PTA), MA (甲醇), PP (聚丙烯), L (塑料)
  - 农产品: M (豆粕), Y (豆油), P (棕榈油), C (玉米)
  - 有色金属: CU (铜), AL (铝), ZN (锌), AU (黄金)

## 注意事项

1. **数据缓存**: 系统会自动缓存数据到SQLite数据库，避免重复请求
2. **请求频率**: 建议在请求之间添加适当延迟，避免被服务器限制
3. **数据质量**: 部分合约可能存在数据缺失，建议使用主力连续合约
4. **回测偏差**: 实际交易中存在滑点、手续费等成本，回测结果仅供参考

## 示例工作流

```bash
# 1. 初始化：获取最近3个月的数据
python strategy_runner.py --variety IF --start 2025-01-01 --end 2025-03-31

# 2. 参数优化：寻找最优参数组合
python big_trader_follow.py --varieties IF --start 2025-01-01 --scan

# 3. 多品种对比
python big_trader_follow.py --varieties IF,IC,IH,IM --start 2025-01-01 --scan

# 4. 每日更新：增量获取最新数据
python strategy_runner.py --variety IF --start 2025-03-30 --end 2025-03-31
```

## 故障排查

### 问题1: 无法获取价格数据

- 检查网络连接
- 确认期货代码格式正确（主力连续用 IF0，具体合约用 IF2504）
- 尝试使用 `--refresh` 参数强制刷新

### 问题2: 持仓数据为空

- 确认日期是交易日（非周末、节假日）
- 检查品种代码是否正确
- 查看日志中的错误信息

### 问题3: 数据库锁定

- 确保没有多个进程同时访问数据库
- 删除 `futures_position.db-journal` 文件后重试

## 技术支持

如有问题，请查看日志文件或联系开发者。
