#!/usr/bin/env python3
"""
期货大户跟单策略执行器
整合价格数据和持仓数据，实现完整的跟单策略
"""
import argparse
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd

import features_position as fp
import price_fetcher as pf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("strategy_runner")

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "strategy_output"


def fetch_top_positions(trade_date: str, variety: str, top_n: int = 20) -> dict:
    """
    获取指定日期的前N大席位持仓数据

    Returns:
        dict with keys: trade_date, variety, main_contract, long_total, short_total, net_position
    """
    # 获取主力合约
    contracts = fp.get_contracts(trade_date, variety)
    if not contracts:
        return None

    main_contract = fp.pick_main_contract(trade_date, contracts)
    if not main_contract:
        return None

    # 获取多头和空头持仓排名
    df_long = fp.get_position(trade_date, main_contract, "LPRANK")
    df_short = fp.get_position(trade_date, main_contract, "SPRANK")

    if df_long is None or df_short is None:
        return None

    # 计算前N大席位的总持仓
    long_total = pd.to_numeric(df_long["LONG_POSITION"].head(top_n), errors="coerce").sum()
    short_total = pd.to_numeric(df_short["SHORT_POSITION"].head(top_n), errors="coerce").sum()
    net_position = long_total - short_total

    return {
        "trade_date": trade_date,
        "variety": variety,
        "main_contract": main_contract,
        "long_total": long_total,
        "short_total": short_total,
        "net_position": net_position,
        "net_ratio": net_position / (long_total + short_total) if (long_total + short_total) > 0 else 0,
    }


def build_position_history(variety: str, start: str, end: str, top_n: int = 20) -> pd.DataFrame:
    """
    构建持仓历史数据

    Returns:
        DataFrame with columns: trade_date, variety, main_contract, long_total, short_total, net_position, net_ratio
    """
    first_available = fp.find_first_available_date(start, end, variety)
    if first_available is None:
        log.warning(f"{variety} 在 {start} 到 {end} 区间没有可用数据")
        return pd.DataFrame()

    records = []
    for d in pd.bdate_range(first_available, end):
        trade_date = d.strftime("%Y-%m-%d")
        position_data = fetch_top_positions(trade_date, variety, top_n)

        if position_data:
            records.append(position_data)

        if len(records) % 10 == 0:
            log.info(f"{variety} 已获取 {len(records)} 个交易日数据")

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


def generate_signals(df: pd.DataFrame, lookback: int = 1, threshold: float = 0.0) -> pd.DataFrame:
    """
    生成交易信号

    Args:
        df: 持仓数据
        lookback: 回看天数
        threshold: 净持仓比例阈值

    Returns:
        DataFrame with signal column: 1=做多, -1=做空, 0=空仓
    """
    df = df.sort_values("trade_date").copy()

    # 计算净持仓变化
    df["net_position_change"] = df["net_position"] - df["net_position"].shift(lookback)
    df["net_ratio_change"] = df["net_ratio"] - df["net_ratio"].shift(lookback)

    # 生成信号
    df["signal"] = 0

    # 做多条件：净持仓比例 > 阈值 且 净持仓增加
    long_cond = (df["net_ratio"] > threshold) & (df["net_position_change"] > 0)
    df.loc[long_cond, "signal"] = 1

    # 做空条件：净持仓比例 < -阈值 且 净持仓减少
    short_cond = (df["net_ratio"] < -threshold) & (df["net_position_change"] < 0)
    df.loc[short_cond, "signal"] = -1

    return df


def backtest_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """
    回测策略

    Args:
        df: 包含信号和价格的DataFrame

    Returns:
        DataFrame with backtest results
    """
    df = df.sort_values("trade_date").copy()

    # 次日开仓（信号延迟1天）
    df["position"] = df["signal"].shift(1).fillna(0)

    # 计算收益：T+1日开盘开仓，T+2日开盘平仓
    # 收益 = (次日开盘价 - 今日开盘价) / 今日开盘价
    df["next_open"] = df["open"].shift(-1)
    df["price_change"] = df["next_open"] - df["open"]
    df["price_return"] = df["price_change"] / df["open"]

    # 策略收益 = 持仓 * 价格变化
    df["strategy_return"] = df["position"] * df["price_return"]

    # 累计收益
    df["cumulative_return"] = (1 + df["strategy_return"]).cumprod()
    df["cumulative_benchmark"] = (1 + df["price_return"]).cumprod()

    # 最大回撤
    df["rolling_max"] = df["cumulative_return"].cummax()
    df["drawdown"] = (df["cumulative_return"] - df["rolling_max"]) / df["rolling_max"]

    return df


def calculate_metrics(df: pd.DataFrame) -> dict:
    """计算策略绩效指标"""
    if df.empty or "strategy_return" not in df.columns:
        return {}

    returns = df["strategy_return"].dropna()
    if len(returns) == 0:
        return {}

    total_return = df["cumulative_return"].iloc[-1] - 1
    annual_factor = 252
    annual_return = (1 + total_return) ** (annual_factor / len(returns)) - 1
    annual_vol = returns.std() * (annual_factor ** 0.5)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    max_drawdown = df["drawdown"].min()

    # 胜率
    win_trades = (returns > 0).sum()
    total_trades = (returns != 0).sum()
    win_rate = win_trades / total_trades if total_trades > 0 else 0

    # 持仓统计
    positions = df["position"]
    long_days = (positions > 0).sum()
    short_days = (positions < 0).sum()
    flat_days = (positions == 0).sum()

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "long_days": long_days,
        "short_days": short_days,
        "flat_days": flat_days,
    }


def run_strategy(variety: str, start: str, end: str, top_n: int = 20, lookback: int = 1, threshold: float = 0.0, refresh: bool = False):
    """
    运行完整策略

    Args:
        variety: 品种代码，如 IF
        start: 开始日期
        end: 结束日期
        top_n: 跟踪前N大席位
        lookback: 回看天数
        threshold: 净持仓比例阈值
        refresh: 是否刷新数据
    """
    log.info(f"{'='*60}")
    log.info(f"运行策略: {variety} | Top{top_n} | 回看{lookback}天 | 阈值{threshold}")
    log.info(f"{'='*60}")

    # 1. 获取持仓数据
    log.info("步骤1: 获取持仓数据...")
    position_df = build_position_history(variety, start, end, top_n)
    if position_df.empty:
        log.error("持仓数据为空，退出")
        return

    log.info(f"获取到 {len(position_df)} 个交易日的持仓数据")

    # 2. 获取价格数据
    log.info("步骤2: 获取价格数据...")
    symbol = f"{variety}0"  # 主力连续合约
    price_df = pf.get_daily_prices(symbol, start, end, refresh=refresh)
    if price_df.empty:
        log.error("价格数据为空，退出")
        return

    log.info(f"获取到 {len(price_df)} 个交易日的价格数据")

    # 3. 合并数据
    log.info("步骤3: 合并持仓和价格数据...")
    df = position_df.merge(price_df, on="trade_date", how="inner")
    log.info(f"合并后共 {len(df)} 个交易日")

    # 4. 生成信号
    log.info("步骤4: 生成交易信号...")
    df = generate_signals(df, lookback, threshold)
    signal_counts = df["signal"].value_counts()
    log.info(f"信号分布: 做多={signal_counts.get(1, 0)} 做空={signal_counts.get(-1, 0)} 空仓={signal_counts.get(0, 0)}")

    # 5. 回测
    log.info("步骤5: 回测策略...")
    df = backtest_strategy(df)

    # 6. 计算指标
    metrics = calculate_metrics(df)
    if metrics:
        log.info("\n策略绩效:")
        log.info(f"  总收益率:   {metrics['total_return']*100:.2f}%")
        log.info(f"  年化收益率: {metrics['annual_return']*100:.2f}%")
        log.info(f"  年化波动率: {metrics['annual_volatility']*100:.2f}%")
        log.info(f"  夏普比率:   {metrics['sharpe_ratio']:.3f}")
        log.info(f"  最大回撤:   {metrics['max_drawdown']*100:.2f}%")
        log.info(f"  胜率:       {metrics['win_rate']*100:.2f}%")
        log.info(f"  交易次数:   {metrics['total_trades']}")
        log.info(f"  做多天数:   {metrics['long_days']}")
        log.info(f"  做空天数:   {metrics['short_days']}")

    # 7. 保存结果
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"{variety}_top{top_n}_lb{lookback}_th{threshold:.2f}_result.csv"
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    log.info(f"\n结果已保存到: {output_file}")

    return df, metrics


def main():
    parser = argparse.ArgumentParser(description="期货大户跟单策略")
    parser.add_argument("--variety", default="IF", help="品种代码，如 IF, I, RB")
    parser.add_argument("--start", default="2025-01-01", help="开始日期")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"), help="结束日期")
    parser.add_argument("--top-n", type=int, default=20, help="跟踪前N大席位")
    parser.add_argument("--lookback", type=int, default=1, help="回看天数")
    parser.add_argument("--threshold", type=float, default=0.0, help="净持仓比例阈值")
    parser.add_argument("--refresh", action="store_true", help="强制刷新数据")
    parser.add_argument("--db", default=str(fp.DEFAULT_DB_PATH), help="数据库路径")
    args = parser.parse_args()

    # 初始化数据库
    fp.init_db(args.db)
    pf.init_db(args.db)

    try:
        run_strategy(
            variety=args.variety,
            start=args.start,
            end=args.end,
            top_n=args.top_n,
            lookback=args.lookback,
            threshold=args.threshold,
            refresh=args.refresh,
        )
    finally:
        fp.close_db()
        pf.close_db()


if __name__ == "__main__":
    main()
