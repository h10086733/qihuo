# 每日市场情绪扫描器使用指南

## 功能说明

每日自动扫描所有期货品种，找出市场情绪**偏多**或**偏空**的品种，帮助你快速发现交易机会。

## 核心功能

1. **自动扫描** - 一键扫描所有品种（股指、黑色系、有色金属、化工、农产品）
2. **情绪判断** - 根据前20大席位的净持仓比例判断市场情绪
3. **一致性分析** - 判断价格变化与持仓方向是否一致
4. **结果分类** - 自动分类为偏多、偏空、中性三类
5. **数据导出** - 自动保存CSV文件，方便进一步分析

## 快速开始

### 方式1：使用自动化脚本（推荐）

```bash
# 一键运行每日扫描
./daily_auto_scan.sh
```

这个脚本会：
1. 自动更新昨天的价格数据
2. 扫描所有品种的市场情绪
3. 生成分类报告（偏多、偏空、中性）
4. 保存结果到CSV文件

### 方式2：手动运行

```bash
# 扫描昨天的数据（默认）
python daily_scanner.py

# 扫描指定日期
python daily_scanner.py --date 2026-03-31

# 先更新数据再扫描
python daily_scanner.py --date 2026-03-31 --update

# 自定义阈值（默认5%）
python daily_scanner.py --date 2026-03-31 --threshold 0.03
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--date` | 扫描日期（YYYY-MM-DD） | 昨天 |
| `--top-n` | 前N大席位 | 20 |
| `--threshold` | 情绪阈值（小数） | 0.05（5%） |
| `--update` | 先更新最新数据 | False |

## 情绪判断标准

### 偏多 🔴
- 净持仓比例 > 阈值（默认5%）
- 表示大户明显偏向做多
- 可能预示价格上涨

### 偏空 🔵
- 净持仓比例 < -阈值（默认-5%）
- 表示大户明显偏向做空
- 可能预示价格下跌

### 中性 ⚪
- 净持仓比例在 -5% 到 +5% 之间
- 表示多空力量相对均衡
- 方向不明确

## 输出文件

扫描完成后会在 `daily_scan_output/` 目录生成以下文件：

### 1. 完整扫描结果
- 文件名：`scan_YYYY-MM-DD.csv`
- 内容：所有品种的完整数据

### 2. 偏多品种
- 文件名：`bullish_YYYY-MM-DD.csv`
- 内容：只包含偏多品种
- 按净持仓比例从高到低排序

### 3. 偏空品种
- 文件名：`bearish_YYYY-MM-DD.csv`
- 内容：只包含偏空品种
- 按净持仓比例从低到高排序

## 实际案例

### 案例：2026-03-31 扫描结果

```
总扫描品种: 13
有持仓数据: 13
偏多品种: 0
偏空品种: 9
中性品种: 4

偏空品种（净持仓比例 < -5.0%）
================================================================================
品种       价格         涨跌幅        净持仓比例        一致性
--------------------------------------------------------------------------------
JM       1148.50        -5.04%     -11.97% ✓
IH       2804.00        -0.50%     -11.28% ✓
FG       1019.00        -1.92%     -10.68% ✓
IM       7379.40        -1.73%      -9.11% ✓
SF       5874.00        -2.59%      -7.74% ✓
IF       4375.80        -1.00%      -7.41% ✓
RB       3121.00        -0.76%      -7.32% ✓
IC       7425.00        -1.89%      -7.23% ✓
SM       6444.00        -1.74%      -6.72% ✓
```

**分析**：
- 当天市场整体偏空，9个品种净持仓为负
- 焦煤(JM)最空，净持仓比例-11.97%
- 所有偏空品种价格都下跌，一致性100%
- 这是一个典型的空头市场

## 使用建议

### 1. 每日例行扫描

建议每天收盘后运行扫描：

```bash
# 方式1：手动运行
./daily_auto_scan.sh

# 方式2：设置定时任务（crontab）
# 每天晚上9点自动运行
0 21 * * * cd /home/qiyun/project/qihuo && ./daily_auto_scan.sh >> scan.log 2>&1
```

### 2. 关注重点品种

- **偏多且一致性✓** - 价格上涨+大户做多，强势品种
- **偏空且一致性✓** - 价格下跌+大户做空，弱势品种
- **偏多但一致性✗** - 价格下跌但大户做多，可能反弹
- **偏空但一致性✗** - 价格上涨但大户做空，可能回调

### 3. 结合其他指标

扫描结果应该结合以下因素综合判断：
- 技术面：支撑位、阻力位、均线系统
- 基本面：供需关系、库存、政策
- 资金面：成交量、持仓量变化
- 市场面：相关品种联动、板块效应

### 4. 风险控制

- 不要仅凭情绪指标就盲目交易
- 设置合理的止损位
- 控制仓位，分散风险
- 关注市场整体趋势

## 高级用法

### 1. 调整阈值

根据市场波动调整阈值：

```bash
# 牛市或震荡市：提高阈值，只关注极端情绪
python daily_scanner.py --threshold 0.08

# 熊市或趋势市：降低阈值，捕捉更多信号
python daily_scanner.py --threshold 0.03
```

### 2. 批量扫描历史数据

```bash
# 扫描最近一周
for i in {1..7}; do
    date=$(date -d "$i days ago" +%Y-%m-%d)
    python daily_scanner.py --date $date
done
```

### 3. 数据分析

使用Python分析扫描结果：

```python
import pandas as pd

# 读取扫描结果
df = pd.read_csv('daily_scan_output/scan_2026-03-31.csv')

# 统计各类别数量
sentiment_counts = df['sentiment'].value_counts()
print(sentiment_counts)

# 找出净持仓比例最高的品种
top_bullish = df.nlargest(5, 'net_ratio')
print(top_bullish[['variety', 'close', 'net_ratio']])

# 找出价格涨幅最大的品种
top_gainers = df.nlargest(5, 'price_change_pct')
print(top_gainers[['variety', 'close', 'price_change_pct']])
```

### 4. 对比分析

对比不同日期的扫描结果，发现趋势变化：

```python
import pandas as pd

# 读取两天的数据
df1 = pd.read_csv('daily_scan_output/scan_2026-03-30.csv')
df2 = pd.read_csv('daily_scan_output/scan_2026-03-31.csv')

# 合并数据
merged = df1.merge(df2, on='variety', suffixes=('_prev', '_curr'))

# 计算净持仓变化
merged['net_ratio_change'] = merged['net_ratio_curr'] - merged['net_ratio_prev']

# 找出净持仓变化最大的品种
print(merged.nlargest(5, 'net_ratio_change')[['variety', 'net_ratio_prev', 'net_ratio_curr', 'net_ratio_change']])
```

## 常见问题

### Q1: 为什么有些品种没有持仓数据？

A: 可能原因：
1. 该品种当天没有交易
2. 持仓数据尚未发布
3. 品种代码错误或已退市

### Q2: 扫描需要多长时间？

A:
- 如果数据已缓存：约1-2分钟
- 如果需要下载数据：约5-10分钟

### Q3: 可以扫描更多品种吗？

A: 可以，编辑 `daily_scanner.py` 中的 `SCAN_VARIETIES` 字典，添加新品种代码。

### Q4: 如何设置每天自动运行？

A: 使用crontab设置定时任务：

```bash
# 编辑crontab
crontab -e

# 添加以下行（每天21:00运行）
0 21 * * * cd /home/qiyun/project/qihuo && ./daily_auto_scan.sh >> scan.log 2>&1
```

### Q5: 扫描结果准确吗？

A: 扫描结果基于真实的持仓数据，但仅供参考：
- 持仓数据有1天延迟
- 大户持仓不代表一定盈利
- 需要结合其他因素综合判断

## 工作流示例

### 每日交易流程

```bash
# 1. 早上：扫描昨天的市场情绪
./daily_auto_scan.sh

# 2. 查看偏多品种
cat daily_scan_output/bullish_2026-03-31.csv

# 3. 查看偏空品种
cat daily_scan_output/bearish_2026-03-31.csv

# 4. 对重点品种进行详细分析
python query_daily.py --variety JM --date 2026-03-31

# 5. 运行策略回测
python big_trader_follow.py --varieties JM --start 2026-01-01 --scan

# 6. 根据分析结果制定交易计划
```

## 总结

每日市场情绪扫描器可以帮助你：

✅ 快速发现市场机会
✅ 了解大户持仓方向
✅ 判断市场整体情绪
✅ 提高交易决策效率

但请记住：
⚠️ 扫描结果仅供参考
⚠️ 需要结合其他分析方法
⚠️ 严格执行风险控制
⚠️ 期货交易有风险，投资需谨慎

---

**祝交易顺利！** 🎯
