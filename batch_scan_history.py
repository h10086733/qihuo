#!/usr/bin/env python3
"""
批量扫描历史交易日
用于初始化60个交易日的历史数据
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import daily_scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("batch_scan")

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "daily_scan_output"


def get_trading_dates(end_date: str, num_days: int = 60):
    """
    获取交易日列表（排除周末）

    Args:
        end_date: 结束日期
        num_days: 需要的交易日数量

    Returns:
        list: 交易日期列表
    """
    end = pd.to_datetime(end_date)
    dates = []
    current = end

    # 往前推，收集足够的交易日（排除周末）
    while len(dates) < num_days:
        # 排除周末（周六=5，周日=6）
        if current.weekday() < 5:
            dates.append(current.strftime("%Y-%m-%d"))
        current -= timedelta(days=1)

    # 反转，从旧到新
    dates.reverse()
    return dates


def check_existing_scans():
    """检查已有的扫描文件"""
    if not OUTPUT_DIR.exists():
        return []

    scan_files = list(OUTPUT_DIR.glob("scan_*.csv"))
    existing_dates = []

    for f in scan_files:
        try:
            date_str = f.stem.replace("scan_", "")
            existing_dates.append(date_str)
        except:
            continue

    return sorted(existing_dates)


def batch_scan(end_date: str = None, num_days: int = 60, skip_existing: bool = True):
    """
    批量扫描历史交易日

    Args:
        end_date: 结束日期（默认为昨天）
        num_days: 扫描的交易日数量（默认60天）
        skip_existing: 是否跳过已存在的扫描结果
    """
    # 确定结束日期
    if end_date is None:
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    log.info("="*80)
    log.info(f"批量历史扫描")
    log.info(f"结束日期: {end_date}")
    log.info(f"扫描天数: {num_days} 个交易日")
    log.info("="*80)

    # 获取交易日列表
    trading_dates = get_trading_dates(end_date, num_days)
    log.info(f"\n生成交易日列表: {len(trading_dates)} 天")
    log.info(f"从 {trading_dates[0]} 到 {trading_dates[-1]}")

    # 检查已有扫描
    existing_dates = check_existing_scans()
    if existing_dates and skip_existing:
        log.info(f"\n已有扫描结果: {len(existing_dates)} 天")
        log.info(f"从 {min(existing_dates)} 到 {max(existing_dates)}")

    # 过滤需要扫描的日期
    if skip_existing:
        dates_to_scan = [d for d in trading_dates if d not in existing_dates]
    else:
        dates_to_scan = trading_dates

    if not dates_to_scan:
        log.info("\n✅ 所有日期都已扫描完成，无需重复扫描")
        return

    log.info(f"\n需要扫描: {len(dates_to_scan)} 天")

    # 批量扫描
    success_count = 0
    fail_count = 0

    for idx, trade_date in enumerate(dates_to_scan, 1):
        log.info(f"\n{'='*80}")
        log.info(f"[{idx}/{len(dates_to_scan)}] 扫描日期: {trade_date}")
        log.info(f"{'='*80}")

        try:
            # 调用daily_scanner扫描
            daily_scanner.scan_all_varieties(trade_date, top_n=20, threshold=0.05)
            success_count += 1
            log.info(f"✅ {trade_date} 扫描完成")
        except Exception as e:
            fail_count += 1
            log.error(f"❌ {trade_date} 扫描失败: {e}")

    # 汇总
    log.info(f"\n{'='*80}")
    log.info(f"批量扫描完成")
    log.info(f"{'='*80}")
    log.info(f"成功: {success_count} 天")
    log.info(f"失败: {fail_count} 天")
    log.info(f"总计: {len(dates_to_scan)} 天")

    # 最终统计
    final_existing = check_existing_scans()
    log.info(f"\n当前共有扫描结果: {len(final_existing)} 天")
    if final_existing:
        log.info(f"日期范围: {min(final_existing)} 到 {max(final_existing)}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="批量扫描历史交易日")
    parser.add_argument("--end-date", help="结束日期（默认为昨天），格式：YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=60, help="扫描的交易日数量（默认60天）")
    parser.add_argument("--force", action="store_true", help="强制重新扫描已有数据")
    args = parser.parse_args()

    batch_scan(
        end_date=args.end_date,
        num_days=args.days,
        skip_existing=not args.force
    )


if __name__ == "__main__":
    main()
