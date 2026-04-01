#!/usr/bin/env python3
"""
每日市场情绪扫描器
自动扫描所有品种，找出市场情绪偏多或偏空的品种
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import price_fetcher as pf
import features_position as fp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("daily_scanner")

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "daily_scan_output"

# 所有主要品种（按类别分组）
SCAN_VARIETIES = {
    "股指期货": ["IF", "IC", "IH", "IM"],
    "黑色系": ["RB", "HC", "I", "J", "JM", "SF", "SM", "FG"],
    "有色金属": ["CU", "AL", "ZN", "PB", "NI", "SN", "AU", "AG"],
    "化工": ["RU", "BU", "FU", "L", "V", "PP", "TA", "MA", "EG", "EB", "PG", "SA", "UR", "NR", "LU", "SC"],
    "农产品": ["C", "CS", "A", "B", "M", "Y", "P", "OI", "RM", "SR", "CF", "CY", "AP", "CJ", "JD", "RR", "LH", "PK"],
}


def get_variety_sentiment(variety: str, trade_date: str, top_n: int = 20, threshold: float = 0.05):
    """
    获取品种的市场情绪

    Args:
        variety: 品种代码
        trade_date: 交易日期
        top_n: 前N大席位
        threshold: 情绪阈值（默认5%）

    Returns:
        dict: 包含价格、持仓、情绪等信息
    """
    try:
        # 获取价格数据
        symbol = f"{variety}0"
        price_df = pf.load_prices_from_db(symbol, trade_date, trade_date)

        if price_df.empty:
            return None

        price_row = price_df.iloc[0]
        price_change = price_row['close'] - price_row['open']
        price_change_pct = (price_change / price_row['open']) * 100

        # 获取持仓数据
        contracts = fp.get_contracts(trade_date, variety)
        if not contracts:
            return {
                "variety": variety,
                "trade_date": trade_date,
                "open": price_row['open'],
                "close": price_row['close'],
                "price_change_pct": price_change_pct,
                "volume": price_row['volume'],
                "has_position": False,
                "sentiment": "未知",
                "net_ratio": None,
            }

        main_contract = fp.pick_main_contract(trade_date, contracts)
        if not main_contract:
            return None

        df_long = fp.get_position(trade_date, main_contract, "LPRANK")
        df_short = fp.get_position(trade_date, main_contract, "SPRANK")

        if df_long is None or df_short is None:
            return None

        # 计算净持仓
        total_long = pd.to_numeric(df_long["LONG_POSITION"].head(top_n), errors="coerce").sum()
        total_short = pd.to_numeric(df_short["SHORT_POSITION"].head(top_n), errors="coerce").sum()
        net_position = total_long - total_short
        net_ratio = net_position / (total_long + total_short) if (total_long + total_short) > 0 else 0

        # 判断市场情绪
        if net_ratio > threshold:
            sentiment = "偏多 🔴"
        elif net_ratio < -threshold:
            sentiment = "偏空 🔵"
        else:
            sentiment = "中性 ⚪"

        # 判断一致性
        consistent = (price_change_pct > 0 and net_ratio > 0) or (price_change_pct < 0 and net_ratio < 0)

        return {
            "variety": variety,
            "trade_date": trade_date,
            "main_contract": main_contract,
            "open": price_row['open'],
            "close": price_row['close'],
            "price_change_pct": price_change_pct,
            "volume": price_row['volume'],
            "has_position": True,
            "total_long": total_long,
            "total_short": total_short,
            "net_position": net_position,
            "net_ratio": net_ratio,
            "sentiment": sentiment,
            "consistent": consistent,
        }

    except Exception as e:
        log.error(f"{variety} 分析失败: {e}")
        return None


def scan_all_varieties(trade_date: str = None, top_n: int = 20, threshold: float = 0.05):
    """
    扫描所有品种的市场情绪

    Args:
        trade_date: 交易日期（默认为最近一个交易日）
        top_n: 前N大席位
        threshold: 情绪阈值
    """
    # 如果没有指定日期，使用最近一个交易日
    if trade_date is None:
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    log.info(f"="*80)
    log.info(f"每日市场情绪扫描 - {trade_date}")
    log.info(f"="*80)

    # 初始化数据库
    pf.init_db()
    fp.init_db(fp.DEFAULT_DB_PATH)

    all_results = []
    bullish_varieties = []  # 偏多品种
    bearish_varieties = []  # 偏空品种

    total_varieties = sum(len(varieties) for varieties in SCAN_VARIETIES.values())
    current = 0

    for category, varieties in SCAN_VARIETIES.items():
        log.info(f"\n【{category}】")

        for variety in varieties:
            current += 1
            log.info(f"[{current}/{total_varieties}] 扫描 {variety}...")

            result = get_variety_sentiment(variety, trade_date, top_n, threshold)

            if result:
                all_results.append(result)

                if result.get("has_position"):
                    sentiment = result["sentiment"]
                    net_ratio = result["net_ratio"]
                    price_change = result["price_change_pct"]

                    log.info(f"  价格: {result['close']:.2f} ({price_change:+.2f}%)  "
                            f"净持仓: {net_ratio:+.2%}  情绪: {sentiment}")

                    # 收集偏多和偏空的品种
                    if "偏多" in sentiment:
                        bullish_varieties.append(result)
                    elif "偏空" in sentiment:
                        bearish_varieties.append(result)
                else:
                    log.info(f"  价格: {result['close']:.2f} ({result['price_change_pct']:+.2f}%)  持仓数据: 无")

    pf.close_db()
    fp.close_db()

    # 生成报告
    generate_report(trade_date, all_results, bullish_varieties, bearish_varieties, threshold)

    return all_results, bullish_varieties, bearish_varieties


def generate_report(trade_date: str, all_results: list, bullish_varieties: list, bearish_varieties: list, threshold: float):
    """生成扫描报告"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"\n" + "="*80)
    log.info(f"扫描结果汇总")
    log.info(f"="*80)

    # 统计
    total_scanned = len(all_results)
    has_position = sum(1 for r in all_results if r.get("has_position"))
    bullish_count = len(bullish_varieties)
    bearish_count = len(bearish_varieties)
    neutral_count = has_position - bullish_count - bearish_count

    log.info(f"\n总扫描品种: {total_scanned}")
    log.info(f"有持仓数据: {has_position}")
    log.info(f"偏多品种: {bullish_count}")
    log.info(f"偏空品种: {bearish_count}")
    log.info(f"中性品种: {neutral_count}")

    # 显示偏多品种
    if bullish_varieties:
        log.info(f"\n" + "="*80)
        log.info(f"偏多品种（净持仓比例 > {threshold:.1%}）")
        log.info(f"="*80)

        # 按净持仓比例排序
        bullish_varieties.sort(key=lambda x: x["net_ratio"], reverse=True)

        log.info(f"\n{'品种':<8} {'价格':<10} {'涨跌幅':<10} {'净持仓比例':<12} {'一致性':<8}")
        log.info("-" * 80)

        for r in bullish_varieties:
            consistent_mark = "✓" if r["consistent"] else "✗"
            log.info(f"{r['variety']:<8} {r['close']:<10.2f} {r['price_change_pct']:>+9.2f}% "
                    f"{r['net_ratio']:>+11.2%} {consistent_mark:<8}")

    # 显示偏空品种
    if bearish_varieties:
        log.info(f"\n" + "="*80)
        log.info(f"偏空品种（净持仓比例 < -{threshold:.1%}）")
        log.info(f"="*80)

        # 按净持仓比例排序（从最空到最不空）
        bearish_varieties.sort(key=lambda x: x["net_ratio"])

        log.info(f"\n{'品种':<8} {'价格':<10} {'涨跌幅':<10} {'净持仓比例':<12} {'一致性':<8}")
        log.info("-" * 80)

        for r in bearish_varieties:
            consistent_mark = "✓" if r["consistent"] else "✗"
            log.info(f"{r['variety']:<8} {r['close']:<10.2f} {r['price_change_pct']:>+9.2f}% "
                    f"{r['net_ratio']:>+11.2%} {consistent_mark:<8}")

    # 保存到CSV
    if all_results:
        df = pd.DataFrame(all_results)

        # 完整数据
        output_file = OUTPUT_DIR / f"scan_{trade_date}.csv"
        df.to_csv(output_file, index=False, encoding="utf-8-sig")
        log.info(f"\n完整扫描结果已保存到: {output_file}")

        # 偏多品种
        if bullish_varieties:
            bullish_df = pd.DataFrame(bullish_varieties)
            bullish_file = OUTPUT_DIR / f"bullish_{trade_date}.csv"
            bullish_df.to_csv(bullish_file, index=False, encoding="utf-8-sig")
            log.info(f"偏多品种已保存到: {bullish_file}")

        # 偏空品种
        if bearish_varieties:
            bearish_df = pd.DataFrame(bearish_varieties)
            bearish_file = OUTPUT_DIR / f"bearish_{trade_date}.csv"
            bearish_df.to_csv(bearish_file, index=False, encoding="utf-8-sig")
            log.info(f"偏空品种已保存到: {bearish_file}")

    log.info(f"\n" + "="*80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="每日市场情绪扫描器")
    parser.add_argument("--date", help="交易日期（默认为昨天），格式：YYYY-MM-DD")
    parser.add_argument("--top-n", type=int, default=20, help="前N大席位（默认20）")
    parser.add_argument("--threshold", type=float, default=0.05, help="情绪阈值（默认5%%）")
    parser.add_argument("--update", action="store_true", help="先更新最新数据再扫描")
    args = parser.parse_args()

    # 确定扫描日期
    if args.date:
        trade_date = args.date
    else:
        # 默认使用昨天
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 如果需要更新数据
    if args.update:
        log.info("正在更新最新数据...")

        # 更新价格数据
        pf.init_db()
        for category, varieties in SCAN_VARIETIES.items():
            for variety in varieties:
                symbol = f"{variety}0"
                try:
                    pf.get_daily_prices(symbol, trade_date, trade_date, refresh=True)
                except Exception as e:
                    log.warning(f"{symbol} 更新失败: {e}")
        pf.close_db()

        log.info("数据更新完成！\n")

    # 执行扫描
    scan_all_varieties(trade_date, args.top_n, args.threshold)


if __name__ == "__main__":
    main()
