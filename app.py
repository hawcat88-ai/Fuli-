import streamlit as st
import requests
import pandas as pd
import numpy as np
import traceback
from datetime import datetime

# ============================================================
# 复利人生 V1.4
# A股实时行情 + 板块轮动扫描 + 交易观察池
#
# 数据源：
# 腾讯财经
#
# 核心：
# 1. 实时行情
# 2. 历史K线
# 3. 技术指标
# 4. 市场环境
# 5. 板块评分
# 6. 自动观察池
# 7. 风险警戒
#
# 暂不启用自动刷新
# ============================================================

st.set_page_config(
    page_title="复利人生 V1.4",
    page_icon="📈",
    layout="wide"
)

TIMEOUT = 10

# ============================================================
# 当前观察板块
# ============================================================

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

    for line in text.split(";"):

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
# 腾讯历史K线
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

    stock_data = data_block.get(symbol)

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
# 单个板块分析
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

    ma20 = float(
        close.tail(20).mean()
    )

    ma60 = float(
        close.tail(60).mean()
    )


    # --------------------------------------------------------
    # 60日高点和回撤
    # --------------------------------------------------------

    high60 = float(
        history["high"]
        .tail(60)
        .max()
    )

    if high60 > 0:

        drawdown = (
            (high60 - price)
            / high60
            * 100
        )

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

    avg_volume = float(
        volume.tail(60).mean()
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
    # 相对大盘
    # --------------------------------------------------------

    relative_strength = (
        realtime["pct"]
        - index_pct
    )


    # ========================================================
    # 趋势状态
    # ========================================================

    if price > ma20 and ma20 > ma60:

        trend = "强势上升"

    elif price > ma20:

        trend = "短线转强"

    elif price < ma20 and ma20 > ma60:

        trend = "回调"

    else:

        trend = "偏弱"


    # ========================================================
    # MACD状态
    # ========================================================

    if macd_hist > 0 and macd_hist > previous_macd_hist:

        macd_status = "动能增强"

    elif macd_hist > 0:

        macd_status = "多头"

    else:

        macd_status = "空头"


    # ========================================================
    # 量能状态
    # ========================================================

    if volume_ratio >= 150:

        volume_status = "明显放量"

    elif volume_ratio >= 120:

        volume_status = "放量"

    elif volume_ratio >= 80:

        volume_status = "正常"

    else:

        volume_status = "缩量"


    # ========================================================
    # 市场相对强弱
    # ========================================================

    if relative_strength >= 2:

        strength_status = "强于大盘"

    elif relative_strength > 0:

        strength_status = "略强于大盘"

    elif relative_strength > -2:

        strength_status = "略弱于大盘"

    else:

        strength_status = "弱于大盘"


    # ========================================================
    # 评分
    #
    # 趋势       25
    # 相对强度   20
    # 量能       20
    # MACD       15
    # RSI        10
    # 回撤       10
    # ========================================================

    score = 0

    reasons = []

    warnings = []


    # --------------------------------------------------------
    # 趋势 25
    # --------------------------------------------------------

    if price > ma20:

        score += 12

        reasons.append(
            "站上MA20"
        )

    else:

        score += 4

        warnings.append(
            "跌破MA20"
        )


    if ma20 > ma60:

        score += 13

        reasons.append(
            "MA20高于MA60"
        )

    else:

        score += 5

        warnings.append(
            "MA20低于MA60"
        )


    # --------------------------------------------------------
    # 相对强度 20
    # --------------------------------------------------------

    if relative_strength >= 3:

        score += 20

        reasons.append(
            "明显强于大盘"
        )

    elif relative_strength >= 1:

        score += 15

        reasons.append(
            "强于大盘"
        )

    elif relative_strength >= 0:

        score += 10

    elif relative_strength >= -2:

        score += 5

        warnings.append(
            "弱于大盘"
        )

    else:

        score += 2

        warnings.append(
            "明显弱于大盘"
        )


    # --------------------------------------------------------
    # 量能 20
    # --------------------------------------------------------

    if 120 <= volume_ratio <= 180:

        score += 20

        reasons.append(
            "健康放量"
        )

    elif 100 <= volume_ratio < 120:

        score += 15

    elif volume_ratio > 180:

        score += 12

        warnings.append(
            "量能过高，注意追涨风险"
        )

    elif volume_ratio >= 70:

        score += 8

    else:

        score += 4

        warnings.append(
            "成交量偏低"
        )


    # --------------------------------------------------------
    # MACD 15
    # --------------------------------------------------------

    if (
        macd_hist > 0
        and macd_hist > previous_macd_hist
    ):

        score += 15

        reasons.append(
            "MACD动能增强"
        )

    elif macd_hist > 0:

        score += 11

        reasons.append(
            "MACD处于多头"
        )

    elif macd_hist <= 0:

        score += 3

        warnings.append(
            "MACD偏弱"
        )


    # --------------------------------------------------------
    # RSI 10
    # --------------------------------------------------------

    if 50 <= rsi <= 68:

        score += 10

        reasons.append(
            "RSI处于健康强势区"
        )

    elif 45 <= rsi < 50:

        score += 7

    elif 68 < rsi <= 75:

        score += 6

        warnings.append(
            "RSI偏高"
        )

    elif rsi > 75:

        score += 3

        warnings.append(
            "RSI过热，谨防追高"
        )

    else:

        score += 3

        warnings.append(
            "RSI偏弱"
        )


    # --------------------------------------------------------
    # 回撤 10
    # --------------------------------------------------------

    if 5 <= drawdown <= 20:

        score += 10

        reasons.append(
            "处于合理回撤区"
        )

    elif drawdown < 5:

        score += 6

        warnings.append(
            "距离60日高点较近"
        )

    elif drawdown <= 30:

        score += 7

    else:

        score += 3

        warnings.append(
            "60日回撤较大"
        )


    score = float(
        min(
            max(score, 0),
            100
        )
    )


    # ========================================================
    # 自动分级
    # ========================================================

    if score >= 80:

        level = "🔥 强势"

    elif score >= 70:

        level = "🟢 重点观察"

    elif score >= 60:

        level = "🟡 普通观察"

    else:

        level = "⚪ 暂不关注"


    # ========================================================
    # 风险警戒
    # ========================================================

    risk_flags = []


    if price < ma20:

        risk_flags.append(
            "跌破MA20"
        )


    if macd_hist < 0:

        risk_flags.append(
            "MACD偏弱"
        )


    if relative_strength < -2:

        risk_flags.append(
            "明显弱于大盘"
        )


    if rsi > 75:

        risk_flags.append(
            "RSI过热"
        )


    if volume_ratio > 200:

        risk_flags.append(
            "异常放量"
        )


    if len(risk_flags) == 0:

        risk_level = "🟢 正常"

    elif len(risk_flags) == 1:

        risk_level = "🟡 注意"

    else:

        risk_level = "🔴 警戒"


    return {

        "板块": name,

        "ETF": code,

        "现价": price,

        "涨跌幅%": realtime["pct"],

        "趋势": trend,

        "MA20": ma20,

        "MA60": ma60,

        "RSI14": rsi,

        "MACD柱": macd_hist,

        "MACD状态": macd_status,

        "量能比%": volume_ratio,

        "量能状态": volume_status,

        "相对上证%": relative_strength,

        "强弱": strength_status,

        "60日回撤%": drawdown,

        "机会评分": score,

        "级别": level,

        "风险": risk_level,

        "理由": "、".join(
            reasons
        ),

        "警戒": "、".join(
            warnings
        ),

        "风险条件": "、".join(
            risk_flags
        )
    }


# ============================================================
# 市场环境
# ============================================================

def analyze_market_environment(
    index,
    df
):

    index_pct = index["pct"]

    positive_count = int(
        (
            df["涨跌幅%"] > 0
        ).sum()
    )

    total = len(df)


    if (
        index_pct >= 1
        and positive_count >= total * 0.6
    ):

        return (
            "🟢 偏强",
            "大盘上涨且观察板块多数上涨"
        )


    if (
        index_pct <= -1
        and positive_count <= total * 0.4
    ):

        return (
            "🔴 偏弱",
            "大盘走弱且多数观察板块下跌"
        )


    return (
        "🟡 震荡",
        "当前市场方向不够明确"
    )


# ============================================================
# 扫描市场
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

    realtime = get_quotes_tencent(
        codes
    )


    index = realtime.get(
        INDEX_CODE
    )


    if not index:

        raise Exception(
            "无法获取上证指数"
        )


    index_pct = index["pct"]


    results = []

    errors = []


    # --------------------------------------------------------
    # 板块分析
    # --------------------------------------------------------

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
            "所有板块分析失败"
        )


    df = pd.DataFrame(
        results
    )


    df = df.sort_values(
        "机会评分",
        ascending=False
    )


    market_status, market_reason = (
        analyze_market_environment(
            index,
            df
        )
    )


    return (
        df,
        index,
        errors,
        market_status,
        market_reason
    )


# ============================================================
# 页面
# ============================================================

st.title(
    "📈 复利人生 V1.4"
)

st.caption(
    "A股板块轮动自动扫描｜交易观察池"
)


st.info(
    """
核心逻辑：

市场环境
↓
板块趋势
↓
相对大盘强弱
↓
量能
↓
MACD
↓
RSI
↓
回撤位置
↓
机会评分
↓
自动进入观察池

注意：本系统用于发现和筛选机会，
不直接代替人工做买卖决定。
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
                errors,
                market_status,
                market_reason
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
            "market_status"
        ] = market_status

        st.session_state[
            "market_reason"
        ] = market_reason

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
# 扫描失败
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


    # ========================================================
    # 市场环境
    # ========================================================

    st.subheader(
        "🌏 当前市场环境"
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
        "市场状态",
        st.session_state[
            "market_status"
        ]
    )


    col4.metric(
        "观察板块",
        len(df)
    )


    st.caption(
        st.session_state[
            "market_reason"
        ]
    )


    st.caption(
        "扫描时间："
        + st.session_state[
            "scan_time"
        ]
    )


    st.divider()


    # ========================================================
    # 观察池
    # ========================================================

    st.subheader(
        "🔥 复利人生自动观察池"
    )


    watchlist = df[
        df["机会评分"] >= 70
    ]


    if len(watchlist) == 0:

        st.warning(
            "当前没有板块达到70分观察标准。"
        )

        st.write(
            "纪律优先：没有机会时，可以选择等待。"
        )

    else:

        st.success(
            f"当前共有 {len(watchlist)} 个板块进入观察池"
        )


        for _, row in watchlist.iterrows():

            with st.container():

                st.markdown(
                    f"""
### {row['板块']}  ·  {row['级别']}

**机会评分：{row['机会评分']:.0f} / 100**

涨跌幅：**{row['涨跌幅%']:+.2f}%**

趋势：**{row['趋势']}**

相对大盘：**{row['强弱']}**

量能：**{row['量能状态']}**

风险状态：**{row['风险']}**

**入选理由：**
{row['理由']}

**警戒：**
{row['警戒'] if row['警戒'] else '暂无明显警戒条件'}
"""
                )

                st.divider()


    # ========================================================
    # 完整排行榜
    # ========================================================

    st.subheader(
        "📊 板块机会排行榜"
    )


    display_df = df[
        [
            "板块",
            "ETF",
            "现价",
            "涨跌幅%",
            "趋势",
            "RSI14",
            "MACD状态",
            "量能比%",
            "强弱",
            "60日回撤%",
            "机会评分",
            "级别",
            "风险"
        ]
    ]


    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )


    # ========================================================
    # 风险警戒排行榜
    # ========================================================

    st.subheader(
        "⚠️ 风险警戒"
    )


    danger = df[
        df["风险"].isin(
            [
                "🟡 注意",
                "🔴 警戒"
            ]
        )
    ]


    if len(danger) == 0:

        st.success(
            "当前观察池没有明显风险警戒。"
        )

    else:

        for _, row in danger.iterrows():

            st.warning(
                f"{row['板块']}｜"
                f"{row['风险']}｜"
                f"{row['风险条件']}"
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
    "复利人生 V1.4｜自动发现机会，不自动替你交易"
)
