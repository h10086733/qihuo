#!/usr/bin/env python3
"""
期货交易建议Web应用
使用Streamlit构建
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import features_position as fp

BASE_DIR = Path(__file__).resolve().parent
SCAN_DIR = BASE_DIR / "daily_scan_output"

# 品种中文名称映射
VARIETY_NAMES = {
    "IF": "沪深300股指", "IC": "中证500股指", "IH": "上证50股指", "IM": "中证1000股指",
    "RB": "螺纹钢", "HC": "热轧卷板", "I": "铁矿石", "J": "焦炭", "JM": "焦煤",
    "SF": "硅铁", "SM": "锰硅", "FG": "玻璃",
    "CU": "铜", "AL": "铝", "ZN": "锌", "PB": "铅", "NI": "镍", "SN": "锡",
    "AU": "黄金", "AG": "白银",
    "RU": "天然橡胶", "BU": "沥青", "FU": "燃料油", "L": "聚乙烯", "V": "PVC",
    "PP": "聚丙烯", "TA": "PTA", "MA": "甲醇", "EG": "乙二醇", "EB": "苯乙烯",
    "PG": "液化石油气", "SA": "纯碱", "UR": "尿素", "NR": "20号胶", "LU": "低硫燃料油", "SC": "原油",
    "C": "玉米", "CS": "玉米淀粉", "A": "黄大豆1号", "B": "黄大豆2号", "M": "豆粕",
    "Y": "豆油", "P": "棕榈油", "OI": "菜籽油", "RM": "菜籽粕", "SR": "白糖",
    "CF": "棉花", "CY": "棉纱", "AP": "苹果", "CJ": "红枣", "JD": "鸡蛋",
    "RR": "粳米", "LH": "生猪", "PK": "花生",
}


def get_latest_scan_date():
    """获取最新的扫描日期"""
    if not SCAN_DIR.exists():
        return None
    scan_files = list(SCAN_DIR.glob("scan_*.csv"))
    if not scan_files:
        return None
    dates = []
    for f in scan_files:
        try:
            date_str = f.stem.replace("scan_", "")
            dates.append(date_str)
        except:
            continue
    return max(dates) if dates else None


def get_all_scan_dates():
    """获取所有可用的扫描日期"""
    if not SCAN_DIR.exists():
        return []
    scan_files = list(SCAN_DIR.glob("scan_*.csv"))
    if not scan_files:
        return []
    dates = []
    for f in scan_files:
        try:
            date_str = f.stem.replace("scan_", "")
            dates.append(date_str)
        except:
            continue
    return sorted(dates, reverse=True)  # 降序排列，最新的在前


def calculate_net_ratio_ma_from_scans(variety: str, trade_date: str, window: int = 60):
    """从历史扫描文件计算净持仓比例的移动平均"""
    try:
        net_ratios = []
        end_date = pd.to_datetime(trade_date)
        start_date = end_date - pd.Timedelta(days=window * 2)

        for d in pd.date_range(start_date, end_date):
            date_str = d.strftime("%Y-%m-%d")
            scan_file = SCAN_DIR / f"scan_{date_str}.csv"
            if not scan_file.exists():
                continue
            df_scan = pd.read_csv(scan_file)
            variety_data = df_scan[df_scan['variety'] == variety]
            if not variety_data.empty and variety_data.iloc[0].get('has_position'):
                net_ratio = variety_data.iloc[0]['net_ratio']
                if pd.notna(net_ratio):
                    net_ratios.append(net_ratio)

        if len(net_ratios) >= window:
            return sum(net_ratios[-window:]) / window, len(net_ratios)
        elif len(net_ratios) > 0:
            return sum(net_ratios) / len(net_ratios), len(net_ratios)
        else:
            return None, 0
    except:
        return None, 0


def get_top_net_members(trade_date: str, variety: str, main_contract: str, direction: str = "long", top_n: int = 5):
    """获取净持仓最大的前N个席位"""
    try:
        df_long = fp.get_position(trade_date, main_contract, "LPRANK")
        df_short = fp.get_position(trade_date, main_contract, "SPRANK")

        if df_long is None or df_short is None:
            return None

        df_long = df_long[["MEMBER_NAME_ABBR", "LONG_POSITION"]].copy()
        df_short = df_short[["MEMBER_NAME_ABBR", "SHORT_POSITION"]].copy()

        df_long["LONG_POSITION"] = pd.to_numeric(df_long["LONG_POSITION"], errors="coerce").fillna(0)
        df_short["SHORT_POSITION"] = pd.to_numeric(df_short["SHORT_POSITION"], errors="coerce").fillna(0)

        df_merged = pd.merge(df_long, df_short, on="MEMBER_NAME_ABBR", how="outer").fillna(0)
        df_merged["net_position"] = df_merged["LONG_POSITION"] - df_merged["SHORT_POSITION"]

        if direction == "long":
            df_sorted = df_merged.sort_values("net_position", ascending=False)
        else:
            df_sorted = df_merged.sort_values("net_position", ascending=True)

        df_top = df_sorted.head(top_n).copy()
        df_top.columns = ["席位名称", "多头持仓", "空头持仓", "净持仓"]
        return df_top
    except:
        return None


def load_data(trade_date):
    """加载数据"""
    bullish_file = SCAN_DIR / f"bullish_{trade_date}.csv"
    bearish_file = SCAN_DIR / f"bearish_{trade_date}.csv"

    all_varieties = []
    data_points_count = 0  # 记录历史数据点数量

    # 加载做多数据
    if bullish_file.exists():
        df_bullish = pd.read_csv(bullish_file)
        for idx, row in df_bullish.iterrows():
            variety = row['variety']
            net_ratio = row['net_ratio']
            net_ratio_ma60, data_points = calculate_net_ratio_ma_from_scans(variety, trade_date, 60)

            if data_points > data_points_count:
                data_points_count = data_points

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
            variety_data['direction'] = "做多"
            variety_data['name'] = VARIETY_NAMES.get(variety, variety)
            variety_data['data_points'] = data_points
            all_varieties.append(variety_data)

    # 加载做空数据
    if bearish_file.exists():
        df_bearish = pd.read_csv(bearish_file)
        for idx, row in df_bearish.iterrows():
            variety = row['variety']
            net_ratio = row['net_ratio']
            net_ratio_ma60, data_points = calculate_net_ratio_ma_from_scans(variety, trade_date, 60)

            if data_points > data_points_count:
                data_points_count = data_points

            if net_ratio_ma60 is not None:
                change_pct = abs(net_ratio - net_ratio_ma60)
                if change_pct < 0.01:
                    sentiment_change = "稳定"
                elif net_ratio < net_ratio_ma60:
                    sentiment_change = "加强"
                else:
                    sentiment_change = "减弱"
            else:
                sentiment_change = "N/A"

            variety_data = row.to_dict()
            variety_data['ma60'] = net_ratio_ma60
            variety_data['sentiment_change'] = sentiment_change
            variety_data['direction'] = "做空"
            variety_data['name'] = VARIETY_NAMES.get(variety, variety)
            variety_data['data_points'] = data_points
            all_varieties.append(variety_data)

    return pd.DataFrame(all_varieties), data_points_count


# 页面配置
st.set_page_config(
    page_title="期货交易建议",
    page_icon="📊",
    layout="wide"
)

# 标题
st.title("📊 期货交易建议系统")

# 获取所有可用日期
all_dates = get_all_scan_dates()

if not all_dates:
    st.error("❌ 没有找到扫描数据，请先运行 daily_scanner.py")
    st.stop()

# 日期选择器
col1, col2 = st.columns([3, 1])
with col1:
    selected_date = st.selectbox(
        "选择日期",
        options=all_dates,
        index=0,  # 默认选择最新日期
        help="选择要查看的交易日期"
    )
with col2:
    st.metric("可用日期数", len(all_dates))

trade_date = selected_date

st.info(f"📅 当前查看日期: {trade_date}")

# 加载数据
with st.spinner("正在加载数据..."):
    df, data_points_count = load_data(trade_date)

if df.empty:
    st.error("❌ 没有数据")
    st.stop()

# 数据充足性警告
if data_points_count < 60:
    st.warning(f"⚠️ 历史数据不足：仅有 {data_points_count} 个交易日的数据，建议至少60个交易日才能准确计算60日均值。情绪变化判断可能不准确。")

# 排序
sentiment_order = {"加强": 0, "稳定": 1, "减弱": 2, "N/A": 3}
df['sentiment_order'] = df['sentiment_change'].map(sentiment_order)
df = df.sort_values(['sentiment_order', 'net_ratio'], ascending=[True, False], key=lambda x: x if x.name != 'net_ratio' else abs(x))

# 侧边栏筛选
st.sidebar.header("筛选条件")

# 方向筛选
direction_filter = st.sidebar.multiselect(
    "方向",
    options=["做多", "做空"],
    default=["做多", "做空"]
)

# 情绪变化筛选
sentiment_filter = st.sidebar.multiselect(
    "情绪变化",
    options=["加强", "稳定", "减弱"],
    default=["加强", "稳定", "减弱"]
)

# 应用筛选
df_filtered = df[
    (df['direction'].isin(direction_filter)) &
    (df['sentiment_change'].isin(sentiment_filter))
]

# 显示统计
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("总品种数", len(df_filtered))
with col2:
    st.metric("情绪加强", len(df_filtered[df_filtered['sentiment_change'] == '加强']))
with col3:
    st.metric("情绪稳定", len(df_filtered[df_filtered['sentiment_change'] == '稳定']))
with col4:
    st.metric("情绪减弱", len(df_filtered[df_filtered['sentiment_change'] == '减弱']))

# 主表格
st.subheader("📋 交易建议列表")

# 格式化显示
display_df = df_filtered[[
    'variety', 'name', 'direction', 'net_ratio', 'ma60',
    'price_change_pct', 'sentiment_change'
]].copy()

display_df.columns = ['品种代码', '品种名称', '方向', '净持仓比例', '60日均值', '价格涨跌', '情绪变化']

# 格式化百分比
display_df['净持仓比例'] = display_df['净持仓比例'].apply(lambda x: f"{x:+.2%}")
display_df['60日均值'] = display_df['60日均值'].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else "N/A")
display_df['价格涨跌'] = display_df['价格涨跌'].apply(lambda x: f"{x:+.2f}%")

# 添加情绪符号
sentiment_symbols = {"加强": "↑", "稳定": "→", "减弱": "↓", "N/A": ""}
display_df['情绪变化'] = display_df['情绪变化'].apply(lambda x: f"{x} {sentiment_symbols.get(x, '')}")

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True
)

# 详细信息
st.subheader("🔍 详细信息")

# 初始化数据库
fp.init_db(fp.DEFAULT_DB_PATH)

# 选择品种查看详情
selected_variety = st.selectbox(
    "选择品种查看前5大席位",
    options=df_filtered['variety'].tolist(),
    format_func=lambda x: f"{x} - {VARIETY_NAMES.get(x, x)}"
)

if selected_variety:
    variety_data = df_filtered[df_filtered['variety'] == selected_variety].iloc[0]

    col1, col2 = st.columns(2)

    with col1:
        st.write(f"**品种**: {variety_data['name']} ({variety_data['variety']})")
        st.write(f"**方向**: {variety_data['direction']}")
        st.write(f"**净持仓比例**: {variety_data['net_ratio']:+.2%}")
        st.write(f"**60日均值**: {variety_data['ma60']:+.2%}" if pd.notna(variety_data['ma60']) else "**60日均值**: N/A")

    with col2:
        st.write(f"**价格涨跌**: {variety_data['price_change_pct']:+.2f}%")
        st.write(f"**情绪变化**: {variety_data['sentiment_change']} {sentiment_symbols.get(variety_data['sentiment_change'], '')}")
        st.write(f"**主力合约**: {variety_data.get('main_contract', 'N/A')}")

    # 显示前5大席位
    main_contract = variety_data.get('main_contract')
    if main_contract:
        direction = "long" if variety_data['direction'] == "做多" else "short"
        top_members = get_top_net_members(trade_date, selected_variety, main_contract, direction, 5)

        if top_members is not None and not top_members.empty:
            st.write(f"**前5大{'净多头' if direction == 'long' else '净空头'}席位**:")

            # 格式化显示
            top_members['多头持仓'] = top_members['多头持仓'].apply(lambda x: f"{int(x):,}")
            top_members['空头持仓'] = top_members['空头持仓'].apply(lambda x: f"{int(x):,}")
            top_members['净持仓'] = top_members['净持仓'].apply(lambda x: f"{int(x):+,}")

            st.dataframe(top_members, use_container_width=True, hide_index=True)

fp.close_db()

# 说明
st.markdown("---")
st.markdown("""
### 📖 说明
- **净持仓比例**: 前20大席位的多空净持仓占比，正值偏多，负值偏空
- **60日均值**: 过去60个交易日的净持仓比例平均值
- **价格涨跌**: 当日价格涨跌幅
- **情绪变化**: 对比60日均值，加强↑表示情绪增强，减弱↓表示情绪减弱，稳定→表示变化<1%
- **建议**: 优先关注情绪加强且净持仓比例绝对值大的品种
""")
