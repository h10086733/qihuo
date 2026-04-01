#!/usr/bin/env python3
"""
生成做多做空建议列表
基于最新的市场情绪扫描结果
"""
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import features_position as fp

BASE_DIR = Path(__file__).resolve().parent
SCAN_DIR = BASE_DIR / "daily_scan_output"

# 品种中文名称映射
VARIETY_NAMES = {
    # 股指期货
    "IF": "沪深300股指",
    "IC": "中证500股指",
    "IH": "上证50股指",
    "IM": "中证1000股指",

    # 黑色系
    "RB": "螺纹钢",
    "HC": "热轧卷板",
    "I": "铁矿石",
    "J": "焦炭",
    "JM": "焦煤",
    "SF": "硅铁",
    "SM": "锰硅",
    "FG": "玻璃",

    # 有色金属
    "CU": "铜",
    "AL": "铝",
    "ZN": "锌",
    "PB": "铅",
    "NI": "镍",
    "SN": "锡",
    "AU": "黄金",
    "AG": "白银",

    # 化工
    "RU": "天然橡胶",
    "BU": "沥青",
    "FU": "燃料油",
    "L": "聚乙烯",
    "V": "PVC",
    "PP": "聚丙烯",
    "TA": "PTA",
    "MA": "甲醇",
    "EG": "乙二醇",
    "EB": "苯乙烯",
    "PG": "液化石油气",
    "SA": "纯碱",
    "UR": "尿素",
    "NR": "20号胶",
    "LU": "低硫燃料油",
    "SC": "原油",

    # 农产品
    "C": "玉米",
    "CS": "玉米淀粉",
    "A": "黄大豆1号",
    "B": "黄大豆2号",
    "M": "豆粕",
    "Y": "豆油",
    "P": "棕榈油",
    "OI": "菜籽油",
    "RM": "菜籽粕",
    "SR": "白糖",
    "CF": "棉花",
    "CY": "棉纱",
    "AP": "苹果",
    "CJ": "红枣",
    "JD": "鸡蛋",
    "RR": "粳米",
    "LH": "生猪",
    "PK": "花生",
}


def calculate_net_ratio_ma_from_scans(variety: str, trade_date: str, window: int = 60):
    """
    从历史扫描文件计算净持仓比例的移动平均

    Args:
        variety: 品种代码
        trade_date: 当前交易日期
        window: 移动平均窗口（默认60天）

    Returns:
        float: 60日净持仓比例均值，如果数据不足返回None
    """
    try:
        # 收集历史扫描文件中的净持仓数据
        net_ratios = []
        end_date = pd.to_datetime(trade_date)
        start_date = end_date - pd.Timedelta(days=window * 2)  # 取更多天数确保有足够数据

        # 遍历历史扫描文件
        for d in pd.date_range(start_date, end_date):
            date_str = d.strftime("%Y-%m-%d")
            scan_file = SCAN_DIR / f"scan_{date_str}.csv"

            if not scan_file.exists():
                continue

            # 读取扫描文件
            df_scan = pd.read_csv(scan_file)

            # 查找该品种的数据
            variety_data = df_scan[df_scan['variety'] == variety]

            if not variety_data.empty and variety_data.iloc[0].get('has_position'):
                net_ratio = variety_data.iloc[0]['net_ratio']
                if pd.notna(net_ratio):
                    net_ratios.append(net_ratio)

        # 计算移动平均（取最近window个交易日）
        if len(net_ratios) >= window:
            return sum(net_ratios[-window:]) / window
        elif len(net_ratios) > 0:
            # 数据不足window天，返回现有数据的平均值
            return sum(net_ratios) / len(net_ratios)
        else:
            return None

    except Exception as e:
        print(f"计算 {variety} 净持仓均值失败: {e}")
        return None


def get_latest_scan_date():
    """获取最新的扫描日期"""
    if not SCAN_DIR.exists():
        return None

    scan_files = list(SCAN_DIR.glob("scan_*.csv"))
    if not scan_files:
        return None

    # 从文件名提取日期
    dates = []
    for f in scan_files:
        try:
            date_str = f.stem.replace("scan_", "")
            dates.append(date_str)
        except:
            continue

    if not dates:
        return None

    return max(dates)


def get_top_net_members(trade_date: str, variety: str, main_contract: str, direction: str = "long", top_n: int = 5):
    """
    获取净持仓最大的前N个席位

    Args:
        trade_date: 交易日期
        variety: 品种代码
        main_contract: 主力合约
        direction: 方向，"long" 表示找净多头最大的，"short" 表示找净空头最大的
        top_n: 前N大席位

    Returns:
        DataFrame with top net position members
    """
    try:
        # 获取多头和空头数据
        df_long = fp.get_position(trade_date, main_contract, "LPRANK")
        df_short = fp.get_position(trade_date, main_contract, "SPRANK")

        if df_long is None or df_short is None:
            return None

        # 合并多空数据，计算净持仓
        df_long = df_long[["MEMBER_NAME_ABBR", "LONG_POSITION"]].copy()
        df_short = df_short[["MEMBER_NAME_ABBR", "SHORT_POSITION"]].copy()

        # 转换为数值
        df_long["LONG_POSITION"] = pd.to_numeric(df_long["LONG_POSITION"], errors="coerce").fillna(0)
        df_short["SHORT_POSITION"] = pd.to_numeric(df_short["SHORT_POSITION"], errors="coerce").fillna(0)

        # 合并
        df_merged = pd.merge(
            df_long,
            df_short,
            on="MEMBER_NAME_ABBR",
            how="outer"
        ).fillna(0)

        # 计算净持仓
        df_merged["net_position"] = df_merged["LONG_POSITION"] - df_merged["SHORT_POSITION"]

        # 根据方向排序
        if direction == "long":
            # 找净多头最大的（净持仓为正且最大）
            df_sorted = df_merged.sort_values("net_position", ascending=False)
        else:
            # 找净空头最大的（净持仓为负且绝对值最大）
            df_sorted = df_merged.sort_values("net_position", ascending=True)

        # 取前N个
        df_top = df_sorted.head(top_n).copy()
        df_top = df_top[["MEMBER_NAME_ABBR", "LONG_POSITION", "SHORT_POSITION", "net_position"]]
        df_top.columns = ["席位名称", "多头持仓", "空头持仓", "净持仓"]

        return df_top

    except Exception as e:
        print(f"获取净持仓席位信息失败: {e}")
        return None


def generate_recommendations(trade_date: str = None):
    """生成做多做空建议"""

    # 如果没有指定日期，使用最新的扫描结果
    if trade_date is None:
        trade_date = get_latest_scan_date()
        if trade_date is None:
            print("❌ 没有找到扫描结果，请先运行 daily_scanner.py")
            return

    bullish_file = SCAN_DIR / f"bullish_{trade_date}.csv"
    bearish_file = SCAN_DIR / f"bearish_{trade_date}.csv"

    if not bullish_file.exists() and not bearish_file.exists():
        print(f"❌ 没有找到 {trade_date} 的扫描结果")
        return

    print("=" * 80)
    print(f"📊 期货交易建议 - {trade_date}")
    print("=" * 80)

    # 初始化数据库
    fp.init_db(fp.DEFAULT_DB_PATH)

    # 做多建议
    if bullish_file.exists():
        df_bullish = pd.read_csv(bullish_file)
        if not df_bullish.empty:
            # 计算情绪变化并添加到DataFrame
            sentiment_changes = []
            ma60_values = []

            for idx, row in df_bullish.iterrows():
                variety = row['variety']
                net_ratio = row['net_ratio']

                # 计算60日均值
                net_ratio_ma60 = calculate_net_ratio_ma_from_scans(variety, trade_date, 60)
                ma60_values.append(net_ratio_ma60)

                # 判断情绪变化
                if net_ratio_ma60 is not None:
                    change_pct = abs(net_ratio - net_ratio_ma60)
                    if change_pct < 0.01:
                        sentiment_change = "稳定"
                    elif net_ratio > net_ratio_ma60:
                        sentiment_change = "加强"
                    else:
                        sentiment_change = "减弱"
                else:
                    sentiment_change = "N/A"
                sentiment_changes.append(sentiment_change)

            df_bullish['ma60'] = ma60_values
            df_bullish['sentiment_change'] = sentiment_changes

            # 排序：先按情绪变化（加强>稳定>减弱），再按净持仓比例
            sentiment_order = {"加强": 0, "稳定": 1, "减弱": 2, "N/A": 3}
            df_bullish['sentiment_order'] = df_bullish['sentiment_change'].map(sentiment_order)
            df_bullish = df_bullish.sort_values(['sentiment_order', 'net_ratio'], ascending=[True, False])

            print("\n🔴 做多建议（大户情绪偏多）")
            print("-" * 80)
            print(f"{'排名':<6} {'品种代码':<10} {'品种名称':<15} {'净持仓比例':<12} {'60日均值':<12} {'价格涨跌':<10} {'情绪变化':<10}")
            print("-" * 80)

            for rank, (idx, row) in enumerate(df_bullish.iterrows(), 1):
                variety = row['variety']
                name = VARIETY_NAMES.get(variety, variety)
                net_ratio = row['net_ratio']
                price_change = row['price_change_pct']
                ma60 = row['ma60']
                sentiment_change = row['sentiment_change']

                ma60_str = f"{ma60:+.2%}" if ma60 is not None else "N/A"

                # 添加箭头符号
                if sentiment_change == "加强":
                    sentiment_display = "加强 ↑"
                elif sentiment_change == "减弱":
                    sentiment_display = "减弱 ↓"
                elif sentiment_change == "稳定":
                    sentiment_display = "稳定 →"
                else:
                    sentiment_display = "N/A"

                print(f"{rank:<6} {variety:<10} {name:<15} {net_ratio:>+11.2%} {ma60_str:>11} {price_change:>+9.2f}% {sentiment_display:<10}")

                # 显示前5大多头净持仓席位
                main_contract = row.get('main_contract')
                if main_contract:
                    top_members = get_top_net_members(trade_date, variety, main_contract, "long", 5)
                    if top_members is not None and not top_members.empty:
                        print(f"\n  前5大净多头席位：")
                        for idx_m, member in top_members.iterrows():
                            print(f"    {idx_m+1:>2}. {member['席位名称']:<30} 多头: {int(member['多头持仓']):>8,}  空头: {int(member['空头持仓']):>8,}  净持仓: {int(member['净持仓']):>+9,}")
                        print()

    # 做空建议
    if bearish_file.exists():
        df_bearish = pd.read_csv(bearish_file)
        if not df_bearish.empty:
            # 计算情绪变化并添加到DataFrame
            sentiment_changes = []
            ma60_values = []

            for idx, row in df_bearish.iterrows():
                variety = row['variety']
                net_ratio = row['net_ratio']

                # 计算60日均值
                net_ratio_ma60 = calculate_net_ratio_ma_from_scans(variety, trade_date, 60)
                ma60_values.append(net_ratio_ma60)

                # 判断情绪变化（对于做空品种，净持仓减少（更负）表示情绪加强）
                if net_ratio_ma60 is not None:
                    change_pct = abs(net_ratio - net_ratio_ma60)
                    if change_pct < 0.01:
                        sentiment_change = "稳定"
                    elif net_ratio < net_ratio_ma60:  # 更负，空头情绪加强
                        sentiment_change = "加强"
                    else:  # 更正，空头情绪减弱
                        sentiment_change = "减弱"
                else:
                    sentiment_change = "N/A"
                sentiment_changes.append(sentiment_change)

            df_bearish['ma60'] = ma60_values
            df_bearish['sentiment_change'] = sentiment_changes

            # 排序：先按情绪变化（加强>稳定>减弱），再按净持仓比例绝对值
            sentiment_order = {"加强": 0, "稳定": 1, "减弱": 2, "N/A": 3}
            df_bearish['sentiment_order'] = df_bearish['sentiment_change'].map(sentiment_order)
            df_bearish = df_bearish.sort_values(['sentiment_order', 'net_ratio'], ascending=[True, True])

            print("\n🔵 做空建议（大户情绪偏空）")
            print("-" * 80)
            print(f"{'排名':<6} {'品种代码':<10} {'品种名称':<15} {'净持仓比例':<12} {'60日均值':<12} {'价格涨跌':<10} {'情绪变化':<10}")
            print("-" * 80)

            for rank, (idx, row) in enumerate(df_bearish.iterrows(), 1):
                variety = row['variety']
                name = VARIETY_NAMES.get(variety, variety)
                net_ratio = row['net_ratio']
                price_change = row['price_change_pct']
                ma60 = row['ma60']
                sentiment_change = row['sentiment_change']

                ma60_str = f"{ma60:+.2%}" if ma60 is not None else "N/A"

                # 添加箭头符号
                if sentiment_change == "加强":
                    sentiment_display = "加强 ↑"
                elif sentiment_change == "减弱":
                    sentiment_display = "减弱 ↓"
                elif sentiment_change == "稳定":
                    sentiment_display = "稳定 →"
                else:
                    sentiment_display = "N/A"

                print(f"{rank:<6} {variety:<10} {name:<15} {net_ratio:>+11.2%} {ma60_str:>11} {price_change:>+9.2f}% {sentiment_display:<10}")

    # 重点关注：按情绪变化排序的前10个品种
    all_varieties = []

    # 合并做多和做空的数据（已经包含ma60和sentiment_change）
    if bullish_file.exists():
        df_bullish_reload = pd.read_csv(bullish_file)
        if not df_bullish_reload.empty:
            # 重新计算情绪变化
            for idx, row in df_bullish_reload.iterrows():
                variety = row['variety']
                net_ratio = row['net_ratio']
                net_ratio_ma60 = calculate_net_ratio_ma_from_scans(variety, trade_date, 60)

                if net_ratio_ma60 is not None:
                    change_pct = abs(net_ratio - net_ratio_ma60)
                    if change_pct < 0.01:
                        sentiment_change = "稳定"
                    elif net_ratio > net_ratio_ma60:
                        sentiment_change = "加强"
                    else:
                        sentiment_change = "减弱"
                else:
                    sentiment_change = "N/A"

                variety_data = row.to_dict()
                variety_data['ma60'] = net_ratio_ma60
                variety_data['sentiment_change'] = sentiment_change
                all_varieties.append(variety_data)

    if bearish_file.exists():
        df_bearish_reload = pd.read_csv(bearish_file)
        if not df_bearish_reload.empty:
            # 重新计算情绪变化
            for idx, row in df_bearish_reload.iterrows():
                variety = row['variety']
                net_ratio = row['net_ratio']
                net_ratio_ma60 = calculate_net_ratio_ma_from_scans(variety, trade_date, 60)

                if net_ratio_ma60 is not None:
                    change_pct = abs(net_ratio - net_ratio_ma60)
                    if change_pct < 0.01:
                        sentiment_change = "稳定"
                    elif net_ratio < net_ratio_ma60:  # 更负，空头情绪加强
                        sentiment_change = "加强"
                    else:  # 更正，空头情绪减弱
                        sentiment_change = "减弱"
                else:
                    sentiment_change = "N/A"

                variety_data = row.to_dict()
                variety_data['ma60'] = net_ratio_ma60
                variety_data['sentiment_change'] = sentiment_change
                all_varieties.append(variety_data)

    if all_varieties:
        # 排序：先按情绪变化（加强>稳定>减弱），再按净持仓比例绝对值
        sentiment_order = {"加强": 0, "稳定": 1, "减弱": 2, "N/A": 3}
        all_varieties.sort(key=lambda x: (sentiment_order.get(x['sentiment_change'], 3), -abs(x['net_ratio'])))
        top10 = all_varieties[:10]

        print("\n⭐ 重点关注（按情绪变化排序的前10个品种）")
        print("=" * 80)

        for idx, row in enumerate(top10, 1):
            variety = row['variety']
            name = VARIETY_NAMES.get(variety, variety)
            net_ratio = row['net_ratio']
            price_change = row['price_change_pct']
            direction = "做多 🔴" if net_ratio > 0 else "做空 🔵"
            main_contract = row.get('main_contract')
            net_ratio_ma60 = row['ma60']
            sentiment_change = row['sentiment_change']

            ma60_str = f"{net_ratio_ma60:+.2%}" if net_ratio_ma60 is not None else "N/A"

            # 添加箭头符号
            if sentiment_change == "加强":
                sentiment_display = "加强 ↑"
            elif sentiment_change == "减弱":
                sentiment_display = "减弱 ↓"
            elif sentiment_change == "稳定":
                sentiment_display = "稳定 →"
            else:
                sentiment_display = "N/A"

            print(f"\n{idx}. {variety} - {name} | {direction}")
            print(f"   净持仓比例: {net_ratio:+.2%}  |  60日均值: {ma60_str}  |  价格涨跌: {price_change:+.2f}%  |  情绪变化: {sentiment_display}")

            # 显示前5大席位
            if main_contract:
                rank_direction = "long" if net_ratio > 0 else "short"
                top_members = get_top_net_members(trade_date, variety, main_contract, rank_direction, 5)
                if top_members is not None and not top_members.empty:
                    direction_text = "净多头" if net_ratio > 0 else "净空头"
                    print(f"   前5大{direction_text}席位：")
                    for idx_m, member in top_members.iterrows():
                        print(f"     {idx_m+1:>2}. {member['席位名称']:<30} 多头: {int(member['多头持仓']):>8,}  空头: {int(member['空头持仓']):>8,}  净持仓: {int(member['净持仓']):>+9,}")
            print("-" * 80)

    print("\n" + "=" * 80)
    print("说明：")
    print("  • 净持仓比例：前20大席位的多空净持仓占比，正值偏多，负值偏空")
    print("  • 60日均值：过去60个交易日的净持仓比例平均值")
    print("  • 价格涨跌：当日价格涨跌幅")
    print("  • 情绪变化：对比60日均值，加强↑表示情绪增强，减弱↓表示情绪减弱，稳定→表示变化<1%")
    print("  • 建议：优先关注情绪加强且净持仓比例绝对值大的品种，稳定品种可能缺乏动力")
    print("=" * 80)

    # 关闭数据库
    fp.close_db()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="生成做多做空建议")
    parser.add_argument("--date", help="交易日期，格式：YYYY-MM-DD（默认使用最新扫描结果）")
    args = parser.parse_args()

    generate_recommendations(args.date)
