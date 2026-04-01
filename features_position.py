import requests
import pandas as pd
import datetime
import time
import argparse
import logging
import json
import re
import sqlite3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pandas.tseries.offsets import MonthBegin, MonthEnd
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("urllib3").setLevel(logging.ERROR)

BASE_DIR = Path(__file__).resolve().parent
BASE_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
DEFAULT_DB_PATH = BASE_DIR / "futures_position.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://data.eastmoney.com/",
    "Accept": "application/json, */*",
}
TIMEOUT = 10
PROBE_TIMEOUT = 4
MAX_RETRY = 2
PROBE_RETRY = 0


def build_session(max_retry):
    session = requests.Session()
    session.headers.update(HEADERS)

    retry = Retry(
        total=max_retry,
        connect=max_retry,
        read=max_retry,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


SESSION = build_session(MAX_RETRY)
PROBE_SESSION = build_session(PROBE_RETRY)
DB_CONN = None


# =============================
# 工具函数
# =============================
def get_now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db(db_path):
    global DB_CONN

    if DB_CONN is not None:
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    DB_CONN = sqlite3.connect(db_path)
    DB_CONN.row_factory = sqlite3.Row

    DB_CONN.execute(
        """
        CREATE TABLE IF NOT EXISTS contract_cache (
            trade_date TEXT NOT NULL,
            variety TEXT NOT NULL,
            status TEXT NOT NULL,
            contracts_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (trade_date, variety)
        )
        """
    )
    DB_CONN.execute(
        """
        CREATE TABLE IF NOT EXISTS position_cache (
            trade_date TEXT NOT NULL,
            contract TEXT NOT NULL,
            rank_field TEXT NOT NULL,
            status TEXT NOT NULL,
            rows_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (trade_date, contract, rank_field)
        )
        """
    )
    DB_CONN.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_score_cache (
            trade_date TEXT NOT NULL,
            variety TEXT NOT NULL,
            main_contract TEXT NOT NULL,
            score REAL NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (trade_date, variety)
        )
        """
    )
    DB_CONN.commit()


def close_db():
    global DB_CONN

    if DB_CONN is not None:
        DB_CONN.close()
        DB_CONN = None


def load_contract_cache(trade_date, variety):
    if DB_CONN is None:
        return None

    row = DB_CONN.execute(
        "SELECT status, contracts_json FROM contract_cache WHERE trade_date = ? AND variety = ?",
        (trade_date, variety.upper()),
    ).fetchone()
    if row is None:
        return None
    return {
        "status": row["status"],
        "contracts": json.loads(row["contracts_json"]),
    }


def save_contract_cache(trade_date, variety, contracts):
    if DB_CONN is None:
        return

    status = "ok" if contracts else "empty"
    DB_CONN.execute(
        """
        INSERT INTO contract_cache (trade_date, variety, status, contracts_json, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(trade_date, variety) DO UPDATE SET
            status = excluded.status,
            contracts_json = excluded.contracts_json,
            updated_at = excluded.updated_at
        """,
        (trade_date, variety.upper(), status, json.dumps(contracts, ensure_ascii=False), get_now_str()),
    )
    DB_CONN.commit()


def load_position_cache(trade_date, contract, rank_field):
    if DB_CONN is None:
        return None

    row = DB_CONN.execute(
        "SELECT status, rows_json FROM position_cache WHERE trade_date = ? AND contract = ? AND rank_field = ?",
        (trade_date, contract, rank_field),
    ).fetchone()
    if row is None:
        return None
    return {
        "status": row["status"],
        "rows": json.loads(row["rows_json"]),
    }


def save_position_cache(trade_date, contract, rank_field, rows):
    if DB_CONN is None:
        return

    status = "ok" if rows else "empty"
    DB_CONN.execute(
        """
        INSERT INTO position_cache (trade_date, contract, rank_field, status, rows_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(trade_date, contract, rank_field) DO UPDATE SET
            status = excluded.status,
            rows_json = excluded.rows_json,
            updated_at = excluded.updated_at
        """,
        (trade_date, contract, rank_field, status, json.dumps(rows, ensure_ascii=False), get_now_str()),
    )
    DB_CONN.commit()


def load_daily_score_cache(trade_date, variety):
    if DB_CONN is None:
        return None

    row = DB_CONN.execute(
        "SELECT main_contract, score FROM daily_score_cache WHERE trade_date = ? AND variety = ?",
        (trade_date, variety.upper()),
    ).fetchone()
    if row is None:
        return None
    return {
        "contract": row["main_contract"],
        "score": row["score"],
    }


def save_daily_score_cache(trade_date, variety, contract, score):
    if DB_CONN is None:
        return

    DB_CONN.execute(
        """
        INSERT INTO daily_score_cache (trade_date, variety, main_contract, score, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(trade_date, variety) DO UPDATE SET
            main_contract = excluded.main_contract,
            score = excluded.score,
            updated_at = excluded.updated_at
        """,
        (trade_date, variety.upper(), contract, float(score), get_now_str()),
    )
    DB_CONN.commit()


def is_weekend(date_str):
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return d.weekday() >= 5


def request_json(params, quiet=False):
    try:
        session = PROBE_SESSION if quiet else SESSION
        timeout = PROBE_TIMEOUT if quiet else TIMEOUT
        r = session.get(BASE_URL, params=params, timeout=timeout)
        r.raise_for_status()
        text = r.text.strip()

        if text.startswith("jQuery"):
            match = re.match(r"^[^(]+\((.*)\)\s*;?$", text, flags=re.S)
            if match:
                text = match.group(1)

        data = json.loads(text)

        if data.get("code") == 9201:
            return {"result": {"data": [], "count": 0}, "success": True, "code": 9201}

        if not data.get("success", True):
            if quiet:
                return None
            logging.error(f"API错误: {data}")
            return None

        return data

    except Exception as e:
        if quiet:
            return None
        else:
            logging.error(f"请求异常: {e}")
        return None


# =============================
# 获取某天所有合约
# =============================
def get_contracts(trade_date, variety, page_size=500, quiet=False, refresh=False):
    variety = variety.upper()

    if not refresh:
        cached = load_contract_cache(trade_date, variety)
        if cached is not None:
            return cached["contracts"]

    params = {
        "reportName": "RPT_FUTU_DAILYPOSITION",
        "columns": "SECURITY_CODE,TRADE_CODE,VOLUMERANK",
        "filter": f"(TRADE_DATE='{trade_date}')(TYPE=\"0\")(VOLUMERANK=1)(TRADE_CODE=\"{variety}\")",
        "sortColumns": "SECURITY_CODE",
        "sortTypes": "1",
        "pageNumber": "1",
        "pageSize": str(page_size),
        "source": "WEB",
        "client": "WEB",
    }

    data = request_json(params, quiet=quiet)
    if data is None:
        return []

    if not data.get("result"):
        save_contract_cache(trade_date, variety, [])
        return []

    rows = data["result"]["data"]
    contracts = {r.get("SECURITY_CODE") for r in rows if r.get("SECURITY_CODE")}
    contracts = sorted(contracts)
    save_contract_cache(trade_date, variety, contracts)
    return contracts


def has_contracts(trade_date, variety):
    return bool(get_contracts(trade_date, variety, page_size=1, quiet=True))


def month_probe_days(start_dt, end_dt):
    days = list(pd.bdate_range(start_dt, end_dt))
    if not days:
        return []

    indices = sorted({0, len(days) // 2, len(days) - 1})
    return [days[i] for i in indices]


def month_has_data(month_start, start_dt, end_dt, variety):
    window_start = max(month_start, start_dt)
    window_end = min(month_start + MonthEnd(0), end_dt)

    for probe_day in month_probe_days(window_start, window_end):
        if has_contracts(probe_day.strftime("%Y-%m-%d"), variety):
            return True

    return False


def find_first_available_date(start, end, variety):
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)
    months = []
    current = pd.Timestamp(start_dt.year, start_dt.month, 1)
    while current <= end_dt:
        months.append(current)
        current = current + MonthBegin(1)

    if not months:
        return None

    month_cache = {}

    def check_month(index):
        if index not in month_cache:
            month_cache[index] = month_has_data(months[index], start_dt, end_dt, variety)
        return month_cache[index]

    right = None
    for index in range(len(months) - 1, -1, -1):
        if check_month(index):
            right = index
            break

    if right is None:
        return None

    left = 0
    while left < right:
        mid = (left + right) // 2
        if check_month(mid):
            right = mid
        else:
            left = mid + 1

    window_start = max(months[left], start_dt)
    window_end = min(months[left] + MonthEnd(0), end_dt)
    for trade_day in pd.bdate_range(window_start, window_end):
        trade_date = trade_day.strftime("%Y-%m-%d")
        if has_contracts(trade_date, variety):
            return trade_date

    return None


# =============================
# 获取持仓数据
# =============================
def get_position(trade_date, contract, rank_field, refresh=False):
    if not refresh:
        cached = load_position_cache(trade_date, contract, rank_field)
        if cached is not None:
            rows = cached["rows"]
            if not rows:
                return None
            return pd.DataFrame(rows)

    params = {
        "reportName": "RPT_FUTU_DAILYPOSITION",
        "columns": "SECURITY_CODE,MEMBER_NAME_ABBR,VOLUME,LONG_POSITION,SHORT_POSITION,VOLUMERANK,LPRANK,SPRANK",
        "filter": f"(SECURITY_CODE=\"{contract}\")(TRADE_DATE='{trade_date}')(TYPE=\"0\")({rank_field}<>9999)",
        "sortTypes": "1",
        "sortColumns": rank_field,
        "pageNumber": "1",
        "pageSize": "20",
        "source": "WEB",
        "client": "WEB",
    }

    data = request_json(params)

    if not data:
        return None

    if not data.get("result"):
        save_position_cache(trade_date, contract, rank_field, [])
        logging.warning(f"{contract} ❌")
        return None

    rows = data["result"]["data"]

    if not rows:
        save_position_cache(trade_date, contract, rank_field, [])
        return None

    save_position_cache(trade_date, contract, rank_field, rows)
    df = pd.DataFrame(rows)
    return df


# =============================
# 主力识别（按成交量）
# =============================
def pick_main_contract(trade_date, contracts, refresh=False):
    best_contract = None
    best_volume = 0

    for c in contracts:
        df = get_position(trade_date, c, "VOLUMERANK", refresh=refresh)
        if df is None:
            continue

        vol = pd.to_numeric(df["VOLUME"], errors="coerce").sum()

        if vol > best_volume:
            best_volume = vol
            best_contract = c

    return best_contract


# =============================
# 主力行为分析
# =============================
def analyze(trade_date, contract, refresh=False):
    try:
        df_long = get_position(trade_date, contract, "LPRANK", refresh=refresh)
        df_short = get_position(trade_date, contract, "SPRANK", refresh=refresh)

        if df_long is None or df_short is None:
            return None

        long_open = pd.to_numeric(df_long["LONG_POSITION"], errors="coerce").sum()
        short_open = pd.to_numeric(df_short["SHORT_POSITION"], errors="coerce").sum()

        return long_open - short_open
    except Exception as e:
        logging.error(f"分析失败 {contract}: {e}")
        return None


# =============================
# 回测
# =============================
def run(start, end, variety, refresh=False):
    opened_here = False
    if DB_CONN is None:
        init_db(DEFAULT_DB_PATH)
        opened_here = True

    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)

    first_available = find_first_available_date(start, end, variety)
    if first_available is None:
        logging.warning(f"{variety} 在 {start} 到 {end} 区间未找到可用数据")
        return

    first_available_dt = pd.Timestamp(first_available)
    if first_available_dt > start_dt:
        skipped_end = (first_available_dt - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        logging.warning(
            f"{variety} 在东方财富接口中从 {first_available} 起才查到数据，已跳过 {start} 到 {skipped_end}"
        )
        start_dt = first_available_dt

    try:
        dates = pd.date_range(start_dt, end_dt)

        results = []

        for d in dates:
            trade_date = d.strftime("%Y-%m-%d")

            if is_weekend(trade_date):
                logging.info(f"{trade_date} 周末跳过")
                continue

            logging.info(f"处理 {trade_date}")

            if not refresh:
                cached_score = load_daily_score_cache(trade_date, variety)
                if cached_score is not None:
                    logging.info(f"{trade_date} 命中数据库缓存: {cached_score['contract']}")
                    results.append({
                        "date": trade_date,
                        "contract": cached_score["contract"],
                        "score": cached_score["score"],
                    })
                    continue

            contracts = get_contracts(trade_date, variety, refresh=refresh)

            if not contracts:
                logging.info("无合约数据")
                continue

            logging.info(f"{trade_date} 合约: {contracts}")

            main_contract = pick_main_contract(trade_date, contracts, refresh=refresh)

            if not main_contract:
                continue

            score = analyze(trade_date, main_contract, refresh=refresh)

            if score is None:
                continue

            save_daily_score_cache(trade_date, variety, main_contract, score)

            results.append({
                "date": trade_date,
                "contract": main_contract,
                "score": score
            })

            time.sleep(0.5)

        result_df = pd.DataFrame(results)

        print(result_df.tail())

        result_df.to_csv("result.csv", index=False)
    finally:
        if opened_here:
            close_db()


# =============================
# 主函数
# =============================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--variety", default="IF")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--refresh", action="store_true")

    args = parser.parse_args()

    init_db(args.db)
    try:
        run(args.start, args.end, args.variety, refresh=args.refresh)
    finally:
        close_db()


if __name__ == "__main__":
    main()
