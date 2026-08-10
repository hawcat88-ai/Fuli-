import streamlit as st
import requests
import pandas as pd
import numpy as np
import traceback
from datetime import datetime

# ============================================================
# 复利人生 V1.3
# A股实时行情 + 板块自动扫描 + 机会评分
#
# 数据源：
# 腾讯财经实时行情
#
# 当前阶段：
# 实时行情
# +
# 技术指标
# +
# 板块评分
#
# 暂不启用自动刷新
# ============================================================

st.set_page_config(
    page_title="复利人生 V1.3",
    page_icon="📈",
    layout="wide"
)

# ============================================================
# 基础配置
# ============================================================

TIMEOUT = 10

SECTORS = [
    ("半导体", "512480"),
    ("人工智能", "159819"),
    ("军工", "512660"),
    ("电力", "159611"),
    ("有色金属", "512400"),
]

INDEX_CODE = "000001"


# ============================================================
# 市场代码
# ============================================================

def market_code(code):

    code = str(code)

    if code.startswith(("5", "6", "9")):
        return "sh" + code

    return "sz" + code


# ============================================================
# 腾讯实时行情
# ============================================================

def get_quotes_tencent(codes):

    symbols = ",".join(
        market_code(code)
        for code in codes
    )

    url = (
        "https://qt.gtimg.cn/q="
        + symbols
    )

    response = requests.get(
        url,
        timeout=TIMEOUT,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    text = response.text

    if not text:
        raise Exception(
            "腾讯行情接口返回空内容"
        )

    result = {}

    lines = text.split(";")

    for line in lines:

        line = line.strip()

        if not line:
            continue

        if '="' not in line:
            continue

        try:

            left, right = line.split(
                '="',
                1
            )

            symbol = (
                left
                .replace("v_", "")
                .strip()
            )

            values = (
                right
                .rstrip('"')
                .split("~")
            )

            if len(values) < 6:
                continue

            name = values[1]

            price = float(values[3])

            yesterday = float(values[4])

            change = float(values[5])

            if yesterday != 0:

                pct = (
                    (price - yesterday)
                    / yesterday
                    * 100
                )

            else:

                pct = 0

            code = symbol[-6:]

            result[code] = {
                "name": name,
                "price": price,
                "change": change,
                "pct": pct
            }

        except Exception:

            continue

    if not result:

        raise Exception(
            "腾讯行情接口没有解析出有效数据"
        )

    return result


# ============================================================
# 获取历史K线
#
# 这里使用腾讯历史行情接口
# ============================================================

def get_history_tencent(code):

    symbol = market_code(code)

    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/"
        "fqkline/get"
        f"?param={symbol},day,,,120,qfq"
    )

    response = requests.get(
        url,
        timeout=TIMEOUT,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    data = response.json()

    data_block = data.get("data")

    if not data_block:
        raise Exception(
            f"{code} 历史行情返回为空"
        )

    stock_data = data_block.get(
        symbol
    )

    if not stock_data:
        raise Exception(
            f"{code} 找不到历史行情"
        )

    rows = None

    if "qfqday" in stock_data:

        rows = stock_data["qfqday"]

    elif "day" in stock_data:

        rows = stock_data["day"]

    if not rows:

        raise Exception(
            f"{code} 没有K线数据"
        )

    result = []

    for row in rows:

        try:

            if len(row) < 6:
                continue

            result.append({
                "date": row[0],
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[3]),
                "low": float(row[4]),
                "volume": float(row[5])
            })

        except Exception:

            continue

    if len(result) < 60:

        raise Exception(
            f"{code} 有效历史K线不足60根"
        )

    return pd.DataFrame(result)


# ============================================================
# RSI
# ============================================================

def calculate_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = (
        gain
        .rolling(period)
        .mean()
    )

    avg_loss = (
        loss
        .rolling(period)
        .mean()
    )

    rs = (
        avg_gain
        / avg_loss.replace(
            0,
            np.nan
        )
    )

    rsi = (
        100
        - 100 / (1 + rs)
    )

    return rsi


# ============================================================
# MACD
# ============================================================

def calculate_macd(close):

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    dif = ema12 - ema26

    dea = dif.ewm(
        span=9,
        adjust=False
    ).mean()

    hist = dif - dea

    return dif, dea, hist


# ============================================================
# 板块分析
# ============================================================

def analyze_sector(
    name,
    code,
    realtime,
    history,
    index_pct
):

    close = history["close"]

    volume = history["volume"]

    price = realtime["price"]


    # --------------------------------------------------------
    # MA
    # --------------------------------------------------------

    ma20 = (
        close
        .tail(20)
        .mean()
    )

    ma60 = (
        close
        .tail(60)
        .mean()
    )


    # --------------------------------------------------------
    # 60日最高价
    # --------------------------------------------------------

    high60 = (
        history["high"]
        .tail(60)
        .max()
    )


    if high60 > 0:

        drawdown = (
            high60 - price
        ) / high60 * 100

    else:

        drawdown = 0


    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi_series = calculate_rsi(
        close
    )

    rsi = float(
        rsi_series.iloc[-1]
    )


    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    dif, dea, hist = (
        calculate_macd(
            close
        )
    )

    macd_hist = float(
        hist.iloc[-1]
    )

    previous_macd_hist = float(
        hist.iloc[-2]
    )


    # --------------------------------------------------------
    # 量能
    # --------------------------------------------------------

    avg_volume = (
        volume
        .tail(60)
        .mean()
    )

    if avg_volume > 0:

        volume_ratio = (
            volume.iloc[-1]
            / avg_volume
            * 100
        )

    else:

        volume_ratio = 0


    # --------------------------------------------------------
    # 相对上证
    # --------------------------------------------------------

    relative_strength = (
        realtime["pct"]
        - index_pct
    )


    # ========================================================
    # 评分
    # ========================================================

    score = 0

    reasons = []


    # --------------------------------------------------------
    # 1. MA趋势
    # --------------------------------------------------------

    if price > ma20:

        score += 15

        reasons.append(
            "站上MA20"
        )

    else:

        score += 5


    if ma20 > ma60:

        score += 15

        reasons.append(
            "MA20高于MA60"
        )

    else:

        score += 5


    # --------------------------------------------------------
    # 2. RSI
    # --------------------------------------------------------

    if 50 <= rsi <= 70:

        score += 15

        reasons.append(
            "RSI处于强势区"
        )

    elif 40 <= rsi < 50:

        score += 8

    elif rsi > 70:

        score += 5

        reasons.append(
            "RSI偏高"
        )

    else:

        score += 3


    # --------------------------------------------------------
    # 3. MACD
    # --------------------------------------------------------

    if macd_hist > 0:

        score += 15

        reasons.append(
            "MACD红柱"
        )

    else:

        score += 5


    if macd_hist > previous_macd_hist:

        score += 5

        reasons.append(
            "MACD动能增强"
        )


    # --------------------------------------------------------
    # 4. 量能
    # --------------------------------------------------------

    if volume_ratio >= 120:

        score += 15

        reasons.append(
            "成交量明显放大"
        )

    elif volume_ratio >= 90:

        score += 10

    else:

        score += 5


    # --------------------------------------------------------
    # 5. 相对大盘
    # --------------------------------------------------------

    if relative_strength >= 2:

        score += 10

        reasons.append(
            "明显强于大盘"
        )

    elif relative_strength > 0:

        score += 7

        reasons.append(
            "强于大盘"
        )

    else:

        score += 3


    # --------------------------------------------------------
    # 限制最高100
    # --------------------------------------------------------

    score = min(
        float(score),
        100
    )


    # ========================================================
    # 状态
    # ========================================================

    if score >= 80:

        status = "🔥 强势"

    elif score >= 70:

        status = "🟢 值得观察"

    elif score >= 60:

        status = "🟡 观察"

    else:

        status = "⚪ 偏弱"


    # ========================================================
    # 返回结果
    # ========================================================

    return {

        "板块": name,

        "ETF": code,

        "现价": price,

        "涨跌幅%": realtime["pct"],

        "MA20": ma20,

        "MA60": ma60,

        "RSI14": rsi,

        "MACD柱": macd_hist,

        "量能比%": volume_ratio,

        "60日回撤%": drawdown,

        "相对上证%": relative_strength,

        "机会评分": score,

        "状态": status,

        "理由": "、".join(
            reasons
        )
    }


# ============================================================
# 全市场扫描
# ============================================================

def scan_market():

    codes = [
        INDEX_CODE
    ]

    for name, code in SECTORS:

        codes.append(code)


    # --------------------------------------------------------
    # 实时行情
    # --------------------------------------------------------

    realtime = (
        get_quotes_tencent(
            codes
        )
    )


    # --------------------------------------------------------
    # 上证指数
    # --------------------------------------------------------

    index = realtime.get(
        INDEX_CODE
    )

    if not index:

        raise Exception(
            "无法获取上证指数"
        )


    index_pct = index["pct"]


    # --------------------------------------------------------
    # 板块逐个分析
    # --------------------------------------------------------

    results = []

    errors = []


    for name, code in SECTORS:

        try:

            item = realtime.get(
                code
            )

            if not item:

                raise Exception(
                    "实时行情不存在"
                )


            history = (
                get_history_tencent(
                    code
                )
            )


            result = analyze_sector(
                name,
                code,
                item,
                history,
                index_pct
            )


            results.append(
                result
            )


        except Exception as e:

            errors.append(
                f"{name}：{str(e)}"
            )


    if not results:

        raise Exception(
            "所有板块历史数据获取失败"
        )


    df = pd.DataFrame(
        results
    )


    df = df.sort_values(
        "机会评分",
        ascending=False
    )


    return (
        df,
        index,
        errors
    )


# ============================================================
# 页面标题
# ============================================================

st.title(
    "📈 复利人生 V1.3"
)

st.caption(
    "A股实时行情 + 板块自动扫描 + 机会评分"
)


st.info(
    """
数据源：腾讯财经

当前流程：

实时行情
↓
历史K线
↓
技术指标
↓
板块评分
↓
自动排序
↓
寻找值得观察的板块
"""
)


# ============================================================
# 扫描按钮
# ============================================================

if st.button(
    "🔍 立即扫描 A股板块",
    type="primary"
):

    st.session_state.pop(
        "scan_error",
        None
    )

    try:

        with st.spinner(
            "正在扫描 A股市场..."
        ):

            (
                df,
                index,
                errors
            ) = scan_market()


        st.session_state[
            "scan_df"
        ] = df

        st.session_state[
            "scan_index"
        ] = index

        st.session_state[
            "scan_errors"
        ] = errors

        st.session_state[
            "scan_time"
        ] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )


    except Exception:

        st.session_state[
            "scan_error"
        ] = traceback.format_exc()


# ============================================================
# 错误显示
# ============================================================

if "scan_error" in st.session_state:

    st.error(
        "🔴 扫描失败"
    )

    st.code(
        st.session_state[
            "scan_error"
        ],
        language="text"
    )


# ============================================================
# 扫描成功
# ============================================================

if "scan_df" in st.session_state:

    df = st.session_state[
        "scan_df"
    ]

    index = st.session_state[
        "scan_index"
    ]


    # --------------------------------------------------------
    # 市场概览
    # --------------------------------------------------------

    st.success(
        "🟢 A股行情扫描完成"
    )


    col1, col2, col3, col4 = (
        st.columns(4)
    )


    col1.metric(
        "上证指数",
        f"{index['price']:.2f}"
    )


    col2.metric(
        "上证涨跌",
        f"{index['pct']:+.2f}%"
    )


    col3.metric(
        "扫描板块",
        len(df)
    )


    col4.metric(
        "最高评分",
        f"{df['机会评分'].max():.0f}"
    )


    st.caption(
        "扫描时间："
        + st.session_state[
            "scan_time"
        ]
    )


    st.divider()


    # ========================================================
    # 第一名
    # ========================================================

    top = df.iloc[0]


    st.subheader(
        "🏆 当前第一观察板块"
    )


    st.markdown(
        f"""
### {top['板块']}

**机会评分：{top['机会评分']:.0f} / 100**

状态：**{top['状态']}**

当前涨跌：**{top['涨跌幅%']:+.2f}%**

主要理由：

{top['理由']}
"""
    )


    st.divider()


    # ========================================================
    # 自动筛选
    # ========================================================

    st.subheader(
        "🔥 自动筛选结果"
    )


    strong = df[
        df["机会评分"] >= 70
    ]


    if len(strong) == 0:

        st.warning(
            "当前没有板块达到70分观察标准。"
        )

    else:

        st.success(
            f"当前共有 {len(strong)} 个板块进入观察池"
        )


        for _, row in strong.iterrows():

            st.markdown(
                f"""
**{row['板块']}｜{row['状态']}｜{row['机会评分']:.0f}分**

涨跌幅：{row['涨跌幅%']:+.2f}%

RSI：{row['RSI14']:.1f}

量能比：{row['量能比%']:.0f}%

60日回撤：{row['60日回撤%']:.1f}%

理由：{row['理由']}
"""
            )


    st.divider()


    # ========================================================
    # 完整评分表
    # ========================================================

    st.subheader(
        "📊 板块评分排行榜"
    )


    display_df = df[
        [
            "板块",
            "ETF",
            "现价",
            "涨跌幅%",
            "MA20",
            "MA60",
            "RSI14",
            "MACD柱",
            "量能比%",
            "60日回撤%",
            "相对上证%",
            "机会评分",
            "状态"
        ]
    ]


    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )


    # ========================================================
    # 异常数据
    # ========================================================

    errors = st.session_state.get(
        "scan_errors",
        []
    )


    if errors:

        with st.expander(
            "⚠️ 部分板块数据异常"
        ):

            for error in errors:

                st.write(
                    "• " + error
                )


else:

    st.info(
        "点击「🔍 立即扫描 A股板块」开始扫描。"
    )


st.divider()


st.caption(
    "复利人生 V1.3｜先稳定，再自动化"
)
