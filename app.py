import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(
    page_title="复利人生 V1.1",
    page_icon="📈",
    layout="wide"
)

# =========================
# 5个测试板块
# =========================

SECTORS = [
    ("半导体", "512480"),
    ("人工智能", "159819"),
    ("军工", "512660"),
    ("电力", "159611"),
    ("有色金属", "512400"),
]

TIMEOUT = 8


# =========================
# 东方财富市场代码
# =========================

def secid(code):
    if code.startswith(("5", "6")):
        return "1." + code
    return "0." + code


# =========================
# 获取实时行情
# =========================

def get_quotes(codes):

    ids = ",".join(secid(c) for c in codes)

    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get"
        "?fltt=2"
        "&invt=2"
        "&fields=f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18,f124"
        f"&secids={ids}"
    )

    response = requests.get(
        url,
        timeout=TIMEOUT,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    data = response.json().get("data")

    if not data:
        raise RuntimeError("东方财富实时行情返回为空")

    diff = data.get("diff")

    if not diff:
        raise RuntimeError("东方财富行情数据为空")

    if isinstance(diff, list):
        rows = diff
    else:
        rows = list(diff.values())

    result = {}

    for item in rows:

        code = str(item.get("f12") or "")

        if not code:
            continue

        result[code] = {
            "price": float(item.get("f2") or 0),
            "pct": float(item.get("f3") or 0),
            "amount": float(item.get("f6") or 0),
            "time": str(item.get("f124") or "")
        }

    if not result:
        raise RuntimeError("实时行情解析失败")

    return result


# =========================
# 获取日K
# =========================

def get_kline(code):

    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        "?fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        "&klt=101"
        "&fqt=1"
        "&beg=0"
        "&end=20500101"
        "&lmt=120"
        f"&secid={secid(code)}"
    )

    response = requests.get(
        url,
        timeout=TIMEOUT,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    data = response.json().get("data")

    if not data:
        raise RuntimeError(f"{code} K线返回为空")

    rows = data.get("klines")

    if not rows:
        raise RuntimeError(f"{code} 没有K线数据")

    result = []

    for row in rows:

        values = row.split(",")

        if len(values) < 6:
            continue

        try:

            result.append([
                values[0],
                float(values[1]),
                float(values[2]),
                float(values[3]),
                float(values[4]),
                float(values[5])
            ])

        except Exception:
            continue

    if len(result) < 60:
        raise RuntimeError(
            f"{code} 有效K线不足60根"
        )

    return pd.DataFrame(
        result,
        columns=[
            "date",
            "open",
            "close",
            "high",
            "low",
            "volume"
        ]
    )


# =========================
# 计算指标
# =========================

def calculate_sector(
    name,
    code,
    quote,
    kline,
    index_pct
):

    close = kline["close"]
    volume = kline["volume"]

    price = quote["price"]

    if price <= 0:
        price = float(close.iloc[-1])

    # MA
    ma20 = float(
        close.tail(20).mean()
    )

    ma60 = float(
        close.tail(60).mean()
    )

    # 60日最高价
    high60 = float(
        kline["high"].tail(60).max()
    )

    # 回撤
    if high60 > 0:

        drawdown = (
            (high60 - price)
            / high60
            * 100
        )

    else:

        drawdown = 0


    # RSI14

    delta = close.diff().dropna()

    gains = (
        delta
        .clip(lower=0)
        .tail(14)
        .mean()
    )

    losses = (
        -delta
        .clip(upper=0)
        .tail(14)
        .mean()
    )

    if losses == 0:

        rsi = 100

    else:

        rsi = (
            100
            - 100
            / (1 + gains / losses)
        )


    # MACD

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

    macd_hist = float(
        (dif - dea).iloc[-1]
    )


    # 量能比

    avg_volume = float(
        volume.tail(60).mean()
    )

    if avg_volume > 0:

        volume_ratio = (
            float(volume.iloc[-1])
            / avg_volume
            * 100
        )

    else:

        volume_ratio = 0


    # 相对上证

    relative_strength = (
        quote["pct"]
        - index_pct
    )


    # =========================
    # 简单评分
    # =========================

    score = 0


    # 回撤
    score += max(
        0,
        25 - drawdown * 0.6
    )


    # RSI
    score += np.clip(
        (rsi - 35) * 0.35,
        0,
        15
    )


    # 量能
    score += np.clip(
        (volume_ratio - 70) * 0.12,
        0,
        15
    )


    # 相对大盘
    score += np.clip(
        relative_strength * 1.5,
        0,
        15
    )


    # MA20
    if price > ma20:

        score += 15

    else:

        score += 5


    # MACD
    if macd_hist > 0:

        score += 15

    else:

        score += 5


    score = float(
        np.clip(
            score,
            0,
            100
        )
    )


    # 状态

    if (
        price > ma20
        and macd_hist > 0
    ):

        status = "转强"

    elif price > ma20:

        status = "观察"

    else:

        status = "偏弱"


    return {

        "板块": name,

        "ETF": code,

        "现价": price,

        "涨跌幅%": quote["pct"],

        "60日回撤%": drawdown,

        "RSI14": rsi,

        "量能比%": volume_ratio,

        "相对上证%": relative_strength,

        "MA20": ma20,

        "MA60": ma60,

        "MACD柱": macd_hist,

        "状态": status,

        "机会评分": score,

        "数据时间": quote["time"]
    }


# =========================
# 扫描市场
# =========================

def scan_market():

    codes = [
        code
        for name, code in SECTORS
    ]

    # 加入上证指数
    codes.append("000001")

    quotes = get_quotes(codes)

    index_quote = quotes.get("000001")

    if not index_quote:

        raise RuntimeError(
            "无法取得上证指数行情"
        )

    index_pct = index_quote["pct"]

    results = []

    errors = []


    for name, code in SECTORS:

        try:

            quote = quotes.get(code)

            if not quote:

                raise RuntimeError(
                    "实时行情缺失"
                )

            kline = get_kline(code)

            result = calculate_sector(
                name,
                code,
                quote,
                kline,
                index_pct
            )

            results.append(result)

        except Exception as e:

            errors.append(
                f"{name}: {str(e)}"
            )


    if not results:

        raise RuntimeError(
            "5个测试板块均未取得有效数据"
        )

    return (
        pd.DataFrame(results),
        errors,
        index_quote
    )


# =========================
# 页面
# =========================

st.title("📈 复利人生 V1.1")

st.caption(
    "真实 A股行情稳定测试版｜手机 / 平板可直接访问"
)


# =========================
# 扫描按钮
# =========================

if st.button(
    "🔄 立即扫描 A股",
    type="primary"
):

    # 清除上一次错误

    if "fatal" in st.session_state:

        del st.session_state["fatal"]


    try:

        with st.spinner(
            "正在获取真实 A股行情…"
        ):

            df, errors, index = (
                scan_market()
            )


        st.session_state["df"] = df

        st.session_state["errors"] = errors

        st.session_state["index"] = index

        st.session_state["scan_time"] = (
            datetime.now()
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )


except Exception as e:
    import traceback

    st.session_state["fatal"] = (
        str(e)
        + "\n\n完整错误：\n"
        + traceback.format_exc()
    )

# =========================
# 错误
# =========================

if "fatal" in st.session_state:

    st.error(
        "🔴 A股行情连接失败"
    )

    st.code(
        st.session_state["fatal"]
    )

    st.info(
        "本版本不会使用随机数据。"
        "如果行情连接失败，会直接显示真实错误。"
    )


# =========================
# 成功
# =========================

if "df" in st.session_state:

    df = st.session_state["df"]

    index = st.session_state["index"]


    # 按评分排序

    df = df.sort_values(
        "机会评分",
        ascending=False
    )


    st.success(
        f"🟢 实时行情连接成功｜"
        f"东方财富｜"
        f"上证 {index['pct']:+.2f}%"
    )


    # 顶部指标

    col1, col2, col3, col4 = (
        st.columns(4)
    )


    col1.metric(
        "扫描板块",
        len(df)
    )


    col2.metric(
        "最高评分",
        f"{df['机会评分'].max():.1f}"
    )


    col3.metric(
        "当前第一",
        df.iloc[0]["板块"]
    )


    col4.metric(
        "第一涨跌",
        f"{df.iloc[0]['涨跌幅%']:+.2f}%"
    )


    st.caption(
        "扫描时间："
        + st.session_state[
            "scan_time"
        ]
    )


    st.subheader(
        "🔥 板块扫描结果"
    )


    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )


    # 异常板块

    if st.session_state.get(
        "errors"
    ):

        with st.expander(
            "⚠️ 部分板块数据异常"
        ):

            for error in (
                st.session_state["errors"]
            ):

                st.write(
                    "• " + error
                )


else:

    st.info(
        "点击上方「立即扫描 A股」"
        "开始第一次真实行情测试。"
    )
