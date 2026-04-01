#!/usr/bin/env python3
"""
期货价格数据获取模块
支持获取每日开盘价、收盘价、最高价、最低价等
"""
import logging
import time
import ast
import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("price_fetcher")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "futures_position.db"

# 新浪期货日K线接口
SINA_KLINE_URL = "https://stock2.finance.sina.com.cn/futures/api/json.php/InnerFuturesNewService.getDailyKLine"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
    "Accept": "application/json, text/plain, */*",
}

DB_CONN = None
SESSION = None


def init_db(db_path=DEFAULT_DB_PATH):
    """初始化数据库连接"""
    global DB_CONN
    if DB_CONN is not None:
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    DB_CONN = sqlite3.connect(db_path)
    DB_CONN.row_factory = sqlite3.Row

    # 创建价格缓存表
    DB_CONN.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_prices (
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
        """
    )
    DB_CONN.commit()


def close_db():
    """关闭数据库连接"""
    global DB_CONN
    if DB_CONN is not None:
        DB_CONN.close()
        DB_CONN = None


def build_session():
    """构建HTTP会话"""
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_session():
    """获取HTTP会话"""
    global SESSION
    if SESSION is None:
        SESSION = build_session()
    return SESSION


def fetch_daily_prices(symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
    """
    从新浪财经获取期货日K线数据

    Args:
        symbol: 期货代码，如 IF0（主力连续）、IF2504（具体合约）
        start: 开始日期 YYYY-MM-DD
        end: 结束日期 YYYY-MM-DD

    Returns:
        DataFrame with columns: trade_date, open, high, low, close, volume
    """
    params = {"symbol": symbol}

    for attempt in range(1, 4):
        try:
            response = get_session().get(SINA_KLINE_URL, params=params, timeout=20)
            response.raise_for_status()
            text = response.text.strip()

            if not text:
                log.warning(f"{symbol} 返回空数据")
                return pd.DataFrame()

            # 解析JSON数据
            data = response.json() if text else []
            if isinstance(data, str):
                data = ast.literal_eval(data)

            if not data:
                log.warning(f"{symbol} 无价格数据")
                return pd.DataFrame()

            # 转换为DataFrame
            records = []
            for item in data:
                trade_date = item.get("d")
                if not trade_date:
                    continue

                records.append({
                    "trade_date": trade_date,
                    "open": float(item.get("o", 0)),
                    "high": float(item.get("h", 0)),
                    "low": float(item.get("l", 0)),
                    "close": float(item.get("c", 0)),
                    "volume": float(item.get("v", 0)),
                })

            df = pd.DataFrame(records)
            df["trade_date"] = pd.to_datetime(df["trade_date"])

            # 过滤日期范围
            if start:
                df = df[df["trade_date"] >= pd.Timestamp(start)]
            if end:
                df = df[df["trade_date"] <= pd.Timestamp(end)]

            df = df.sort_values("trade_date").reset_index(drop=True)
            log.info(f"{symbol} 获取 {len(df)} 条价格数据")
            return df

        except Exception as e:
            log.error(f"{symbol} 第{attempt}次尝试失败: {e}")
            if attempt < 3:
                time.sleep(attempt)

    return pd.DataFrame()


def save_prices_to_db(df: pd.DataFrame, symbol: str):
    """保存价格数据到数据库"""
    if DB_CONN is None or df.empty:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _, row in df.iterrows():
        DB_CONN.execute(
            """
            INSERT INTO daily_prices (trade_date, symbol, open, high, low, close, volume, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_date, symbol) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                updated_at = excluded.updated_at
            """,
            (
                row["trade_date"].strftime("%Y-%m-%d"),
                symbol,
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"],
                now,
            ),
        )
    DB_CONN.commit()
    log.info(f"{symbol} 保存 {len(df)} 条数据到数据库")


def load_prices_from_db(symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
    """从数据库加载价格数据"""
    if DB_CONN is None:
        return pd.DataFrame()

    query = "SELECT trade_date, open, high, low, close, volume FROM daily_prices WHERE symbol = ?"
    params = [symbol]

    if start:
        query += " AND trade_date >= ?"
        params.append(start)
    if end:
        query += " AND trade_date <= ?"
        params.append(end)

    query += " ORDER BY trade_date"

    rows = DB_CONN.execute(query, params).fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["trade_date", "open", "high", "low", "close", "volume"])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


def get_daily_prices(symbol: str, start: str, end: str, refresh=False) -> pd.DataFrame:
    """
    获取期货每日价格数据（优先从缓存读取）

    Args:
        symbol: 期货代码
        start: 开始日期
        end: 结束日期
        refresh: 是否强制刷新

    Returns:
        DataFrame with columns: trade_date, open, high, low, close, volume
    """
    if not refresh:
        df = load_prices_from_db(symbol, start, end)
        if not df.empty:
            log.info(f"{symbol} 从缓存加载 {len(df)} 条数据")
            return df

    # 从API获取
    df = fetch_daily_prices(symbol, start, end)
    if not df.empty:
        save_prices_to_db(df, symbol)

    return df


def main():
    """命令行测试"""
    import argparse

    parser = argparse.ArgumentParser(description="获取期货每日价格数据")
    parser.add_argument("--symbol", default="IF0", help="期货代码，如 IF0（主力连续）")
    parser.add_argument("--start", default="2025-01-01", help="开始日期")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"), help="结束日期")
    parser.add_argument("--refresh", action="store_true", help="强制刷新数据")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="数据库路径")
    args = parser.parse_args()

    init_db(args.db)
    try:
        df = get_daily_prices(args.symbol, args.start, args.end, refresh=args.refresh)
        if not df.empty:
            print(f"\n获取到 {len(df)} 条数据:")
            print(df.head(10))
            print("...")
            print(df.tail(10))

            # 保存到CSV
            output_file = BASE_DIR / f"{args.symbol}_prices.csv"
            df.to_csv(output_file, index=False, encoding="utf-8-sig")
            print(f"\n数据已保存到: {output_file}")
        else:
            print("未获取到数据")
    finally:
        close_db()


if __name__ == "__main__":
    main()
