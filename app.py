import streamlit as st
import requests
import pandas as pd
import numpy as np
import traceback
from datetime import datetime

# ============================================================
# 复利人生 V1.6
# A股实时行情 + 板块自动扫描
# ============================================================

st.set_page_config(
    page_title="复利人生 V1.6",
    page_icon="📈",
    layout="wide"
)

TIMEOUT = 10


# ============================================================
# 板块观察池"猎手优先级",
# ============================================================

SECTORS = [
    ("半导体", "512480"),
    ("人工智能", "159819"),
    ("科创芯片", "588200"),
    ("通信", "515880"),
    ("计算机", "512720"),
    ("机器人", "562500"),
    ("传媒", "512980"),

    ("军工", "512660"),

    ("电力", "159611"),
    ("公用事业", "159301"),

    ("有色金属", "512400"),
    ("稀土", "159608"),
    ("黄金", "518880"),
    ("煤炭", "515220"),
    ("钢铁", "515210"),
    ("石油", "561360"),

    ("化工", "516020"),

    ("新能源", "516160"),
    ("光伏", "515790"),
    ("新能源车", "515030"),

    ("医药", "512010"),
    ("创新药", "159992"),

    ("证券", "512880"),
    ("银行", "512800"),
    ("金融科技", "159851"),

    ("消费", "159928"),
    ("食品饮料", "515170"),
    ("白酒", "512690"),

    ("汽车", "516110"),
    ("机械", "516960"),

    ("红利", "515180"),
    ("高股息", "563180"),

    ("沪深300", "510300"),
    ("中证1000", "512100"),
    ("创业板", "159915"),
]


# ============================================================
# 四大指数
#
# 特别注意：
# 000001 = 上证指数
# 必须转换成 sh000001
#
# 如果错误转换成 sz000001，
# 得到的其实是平安银行，所以之前才会出现 11.xx。
# ============================================================

INDICES = {
    "上证指数": "000001",
    "深证成指": "399001",
    "创业板指": "399006",
    "科创50": "000688",
}


# ============================================================
# 市场代码转换
# ============================================================

def market_code(code):
    code = str(code).strip()

    index_map = {
        "000001": "sh000001",
        "399001": "sz399001",
        "399006": "sz399006",
        "000688": "sh000688",
    }

    if code in index_map:
        return index_map[code]

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

    url = "https://qt.gtimg.cn/q=" + symbols

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
        raise Exception("腾讯行情接口返回为空")

    result = {}

    for line in text.split(";"):

        line = line.strip()

        if not line or '="' not in line:
            continue

        try:

            left, right = line.split('="', 1)

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
            today_open = float(values[5])

            change = price - yesterday

            # 腾讯接口涨跌幅字段
            if len(values) > 32:

                try:
                    pct = float(values[32])
                except Exception:
                    pct = (
                        change / yesterday * 100
                        if yesterday != 0
                        else 0
                    )

            else:

                pct = (
                    change / yesterday * 100
                    if yesterday != 0
                    else 0
                )

            code = symbol[-6:]

            result[code] = {
                "name": name,
                "price": price,
                "yesterday": yesterday,
                "open": today_open,
                "change": change,
                "pct": pct,
            }

        except Exception:
            continue

    if not result:
        raise Exception("腾讯行情没有解析出有效数据")

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
        raise Exception("历史行情返回为空")

    stock_data = data_block.get(symbol)

    if not stock_data:
        raise Exception("找不到历史行情")

    rows = None

    if "qfqday" in stock_data:
        rows = stock_data["qfqday"]

    elif "day" in stock_data:
        rows = stock_data["day"]

    if not rows:
        raise Exception("没有K线数据")

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
                "volume": float(row[5]),
            })

        except Exception:
            continue

    if len(result) < 60:
        raise Exception("有效历史K线不足60根")

    return pd.DataFrame(result)


# ============================================================
# RSI
# ============================================================

def calculate_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()

    avg_loss = loss.rolling(period).mean()

    rs = (
        avg_gain
        /
        avg_loss.replace(0, np.nan)
    )

    return 100 - 100 / (1 + rs)


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
    market_pct
):

    close = history["close"]
    volume = history["volume"]

    price = realtime["price"]

    # --------------------------------------------------------
    # 均线
    # --------------------------------------------------------

    ma20 = float(
        close.tail(20).mean()
    )

    ma60 = float(
        close.tail(60).mean()
    )

    # --------------------------------------------------------
    # 60日高点
    # --------------------------------------------------------

    high60 = float(
        history["high"].tail(60).max()
    )

    # 这里就是之前发生语法错误的位置
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

    rsi_series = calculate_rsi(close)

    rsi = float(
        rsi_series.iloc[-1]
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    dif, dea, hist = calculate_macd(close)

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
    # 相对市场强度
    # --------------------------------------------------------

    relative_strength = (
        realtime["pct"]
        - market_pct
    )

    # --------------------------------------------------------
    # 趋势
    # --------------------------------------------------------

    if price > ma20 and ma20 > ma60:

        trend = "强势上升"

    elif price > ma20:

        trend = "短线转强"

    elif price < ma20 and ma20 > ma60:

        trend = "回调"

    else:

        trend = "偏弱"

    # --------------------------------------------------------
    # MACD状态
    # --------------------------------------------------------

    if (
        macd_hist > 0
        and macd_hist > previous_macd_hist
    ):

        macd_status = "动能增强"

    elif macd_hist > 0:

        macd_status = "多头"

    else:

        macd_status = "空头"

    # --------------------------------------------------------
    # 量能
    # --------------------------------------------------------

    if volume_ratio >= 150:

        volume_status = "明显放量"

    elif volume_ratio >= 120:

        volume_status = "放量"

    elif volume_ratio >= 80:

        volume_status = "正常"

    else:

        volume_status = "缩量"

    # --------------------------------------------------------
    # 相对市场
    # --------------------------------------------------------

    if relative_strength >= 3:

        strength_status = "明显强于市场"

    elif relative_strength >= 1:

        strength_status = "强于市场"

    elif relative_strength >= 0:

        strength_status = "略强于市场"

    elif relative_strength >= -2:

        strength_status = "略弱于市场"

    else:

        strength_status = "明显弱于市场"

    # --------------------------------------------------------
    # 评分
    # --------------------------------------------------------

    score = 0

    reasons = []

    warnings = []

    # 趋势
    if price > ma20:

        score += 12

        reasons.append("站上MA20")

    else:

        score += 4

        warnings.append("跌破MA20")

    if ma20 > ma60:

        score += 13

        reasons.append("MA20高于MA60")

    else:

        score += 5

        warnings.append("MA20低于MA60")

    # 相对强度
    if relative_strength >= 3:

        score += 20
        reasons.append("明显强于市场")

    elif relative_strength >= 1:

        score += 15
        reasons.append("强于市场")

    elif relative_strength >= 0:

        score += 10

    elif relative_strength >= -2:

        score += 5
        warnings.append("略弱于市场")

    else:

        score += 2
        warnings.append("明显弱于市场")

    # 量能
    if 120 <= volume_ratio <= 180:

        score += 20
        reasons.append("健康放量")

    elif 100 <= volume_ratio < 120:

        score += 15

    elif volume_ratio > 180:

        score += 12
        warnings.append("量能过高")

    elif volume_ratio >= 70:

        score += 8

    else:

        score += 4
        warnings.append("成交量偏低")

    # MACD
    if (
        macd_hist > 0
        and macd_hist > previous_macd_hist
    ):

        score += 15
        reasons.append("MACD动能增强")

    elif macd_hist > 0:

        score += 11
        reasons.append("MACD多头")

    else:

        score += 3
        warnings.append("MACD偏弱")

    # RSI
    if 50 <= rsi <= 68:

        score += 10
        reasons.append("RSI健康")

    elif 45 <= rsi < 50:

        score += 7

    elif 68 < rsi <= 75:

        score += 6
        warnings.append("RSI偏高")

    elif rsi > 75:

        score += 3
        warnings.append("RSI过热")

    else:

        score += 3
        warnings.append("RSI偏弱")

    # 回撤
    if 5 <= drawdown <= 20:

        score += 10
        reasons.append("处于合理回撤区")

    elif drawdown < 5:

        score += 6
        warnings.append("接近60日高点")

    elif drawdown <= 30:

        score += 7

    else:

        score += 3
        warnings.append("60日回撤较大")

    score = min(
        max(float(score), 0),
        100
    )

    # --------------------------------------------------------
    # 等级
    # --------------------------------------------------------

    if score >= 80:

        level = "🔥 强势"

    elif score >= 70:

        level = "🟢 重点观察"

    elif score >= 60:

        level = "🟡 普通观察"

    else:

        level = "⚪ 暂不关注"

    # --------------------------------------------------------
    # 追涨风险
    # --------------------------------------------------------

    chase_flags = []

    if rsi > 75:
        chase_flags.append("RSI过热")

    if volume_ratio > 200:
        chase_flags.append("异常放量")

    if drawdown < 3:
        chase_flags.append("接近60日高点")

    if realtime["pct"] >= 5:
        chase_flags.append("当日涨幅较大")

    if len(chase_flags) >= 2:

        chase_status = "🔴 强势但追涨风险高"

    elif len(chase_flags) == 1:

        chase_status = "🟡 强势，注意追涨"

    else:

        chase_status = "🟢 暂无明显追涨风险"

    # --------------------------------------------------------
    # 风险
    # --------------------------------------------------------

    risk_flags = []

    if price < ma20:
        risk_flags.append("跌破MA20")

    if macd_hist < 0:
        risk_flags.append("MACD偏弱")

    if relative_strength < -2:
        risk_flags.append("明显弱于市场")

    if rsi > 75:
        risk_flags.append("RSI过热")

    if volume_ratio > 200:
        risk_flags.append("异常放量")

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
        "相对市场%": relative_strength,
        "强弱": strength_status,
        "60日回撤%": drawdown,
        "机会评分": score,
        "级别": level,
        "追涨风险": chase_status,
        "追涨条件": "、".join(chase_flags),
        "风险": risk_level,
        "理由": "、".join(reasons),
        "警戒": "、".join(warnings),
        "风险条件": "、".join(risk_flags),
    }


# ============================================================
# 市场环境
# ============================================================

def analyze_market_environment(index_data):

    valid = [
        item
        for item in index_data.values()
        if item is not None
    ]

    if not valid:

        return (
            "🔴 数据异常",
            "主要指数均无法获取",
            0,
            0,
            0
        )

    average_pct = sum(
        item["pct"]
        for item in valid
    ) / len(valid)

    positive = sum(
        1
        for item in valid
        if item["pct"] > 0
    )

    negative = sum(
        1
        for item in valid
        if item["pct"] < 0
    )

    total = len(valid)

    if (
        average_pct >= 1
        and positive >= total * 0.75
    ):

        status = "🟢 强势"
        reason = "主要指数整体上涨，市场风险偏好较强。"

    elif (
        average_pct <= -1
        and negative >= total * 0.75
    ):

        status = "🔴 弱势"
        reason = "主要指数整体走弱，市场风险偏好下降。"

    elif (
        average_pct > 0.3
        and positive > negative
    ):

        status = "🟢 偏强"
        reason = "主要指数多数上涨，市场环境偏积极。"

    elif (
        average_pct < -0.3
        and negative > positive
    ):

        status = "🟠 偏弱"
        reason = "主要指数多数下跌，市场环境偏谨慎。"

    else:

        status = "🟡 震荡"
        reason = "主要指数涨跌分化，暂未形成明确方向。"

    return (
        status,
        reason,
        average_pct,
        positive,
        negative
    )
# ============================================================
# V1.7 猎手模式
# 市场温度系统
# A股颜色逻辑：
# 🔴 强势 / 进攻
# 🟡 震荡 / 等待
# 🟢 弱势 / 防守
# ============================================================

def calculate_market_temperature(index_data):

    valid = [
        item
        for item in index_data.values()
        if item is not None
    ]

    if not valid:
        return {
            "temperature": 0,
            "status": "🟢 防守",
            "description": "指数数据不足，暂不适合进攻。",
            "color": "green"
        }

    # ========================================================
    # 1. 指数涨跌
    # ========================================================

    average_pct = sum(
        item["pct"]
        for item in valid
    ) / len(valid)

    positive_ratio = (
        sum(
            1
            for item in valid
            if item["pct"] > 0
        )
        / len(valid)
    )

    # ========================================================
    # 2. 涨跌幅贡献
    #
    # 平均涨跌幅约：
    # +2% → 强
    #  0% → 中性
    # -2% → 弱
    # ========================================================

    pct_score = (
        50
        + average_pct * 15
    )

    pct_score = max(
        0,
        min(100, pct_score)
    )

    # ========================================================
    # 3. 指数上涨比例
    # ========================================================

    breadth_score = (
        positive_ratio * 100
    )

    # ========================================================
    # 4. 综合市场温度
    # ========================================================

    temperature = (
        pct_score * 0.55
        +
        breadth_score * 0.45
    )

    temperature = round(
        max(
            0,
            min(
                100,
                temperature
            )
        ),
        1
    )

    # ========================================================
    # 5. 市场状态
    #
    # 注意：
    # A股红绿逻辑
    # ========================================================

    if temperature >= 70:

        status = "🔴 进攻"

        description = (
            "市场环境偏强，"
            "可以积极寻找强势板块，"
            "但仍需注意追涨风险。"
        )

        color = "red"

    elif temperature >= 55:

        status = "🟡 震荡偏强"

        description = (
            "市场存在机会，"
            "但板块分化明显，"
            "优先寻找结构性机会。"
        )

        color = "yellow"

    elif temperature >= 45:

        status = "🟡 震荡"

        description = (
            "市场方向不明确，"
            "控制仓位，等待确认。"
        )

        color = "yellow"

    elif temperature >= 30:

        status = "🟢 防守"

        description = (
            "市场偏弱，"
            "降低交易频率，"
            "优先保护本金。"
        )

        color = "green"

    else:

        status = "🟢 防守"

        description = (
            "市场明显偏弱，"
            "以防守为主，"
            "避免盲目抄底。"
        )

        color = "green"

    return {
        "temperature": temperature,
        "status": status,
        "description": description,
        "color": color,
        "average_pct": average_pct,
        "positive_ratio": positive_ratio
    }


# ============================================================
# V1.7 板块猎手评分
# ============================================================

def calculate_hunter_score(row):

    score = 0

    # ========================================================
    # 趋势
    # ========================================================

    if row["趋势"] == "强势上升":

        score += 20

    elif row["趋势"] == "短线转强":

        score += 15

    elif row["趋势"] == "回调":

        score += 8

    else:

        score += 2

    # ========================================================
    # 相对大盘强度
    # ========================================================

    relative = row["相对市场%"]

    if relative >= 3:

        score += 25

    elif relative >= 1.5:

        score += 20

    elif relative >= 0:

        score += 12

    elif relative >= -2:

        score += 6

    else:

        score += 0

    # ========================================================
    # 量能
    # ========================================================

    volume = row["量能比%"]

    if 120 <= volume <= 180:

        score += 20

    elif 100 <= volume < 120:

        score += 15

    elif 80 <= volume < 100:

        score += 10

    elif volume > 180:

        score += 10

    else:

        score += 5

    # ========================================================
    # MACD
    # ========================================================

    if row["MACD状态"] == "动能增强":

        score += 15

    elif row["MACD状态"] == "多头":

        score += 12

    else:

        score += 3

    # ========================================================
    # RSI
    # ========================================================

    rsi = row["RSI14"]

    if 50 <= rsi <= 68:

        score += 10

    elif 45 <= rsi < 50:

        score += 7

    elif 68 < rsi <= 75:

        score += 5

    else:

        score += 2

    # ========================================================
    # 位置
    # ========================================================

    drawdown = row["60日回撤%"]

    if 5 <= drawdown <= 20:

        score += 10

    elif 20 < drawdown <= 30:

        score += 7

    elif drawdown < 5:

        score += 4

    else:

        score += 3

    return round(
        min(
            100,
            max(
                0,
                score
            )
        ),
        0
    )


# ============================================================
# V1.7 自动分类
# ============================================================

def classify_hunter(row):


    score = row["猎手评分"]

    chase = row["追涨风险"]

    risk = row["风险"]

    # ========================================================
    # 风险优先
    # ========================================================

    if risk == "🔴 警戒":

        return "🟢 风险回避"

    # ========================================================
    # 强势但追涨风险高
    # ========================================================

    if chase == "🔴 强势但追涨风险高":

        return "🟠 不宜追涨"

    # ========================================================
    # 评分
    # ========================================================

    if score >= 80:

        return "🔴 重点观察"

    elif score >= 70:

        return "🔴 可以研究"

    elif score >= 60:

        return "🟡 等待确认"

    else:

        return "🟢 回避"
# ============================================================
# V1.7 猎手优先级
# ============================================================

def calculate_hunter_priority(row):

    score = float(
        row.get(
            "猎手评分",
            0
        )
    )

    rsi = float(
        row.get(
            "RSI14",
            50
        )
    )

    volume_ratio = float(
        row.get(
            "量能比%",
            100
        )
    )

    drawdown = float(
        row.get(
            "60日回撤%",
            0
        )
    )

    relative_strength = float(
        row.get(
            "相对市场%",
            0
        )
    )

    priority = score

    # ========================================================
    # 追涨风险扣分
    # ========================================================

    if rsi > 75:

        priority -= 10

    elif rsi > 70:

        priority -= 5

    # ========================================================
    # 异常放量扣分
    # ========================================================

    if volume_ratio > 200:

        priority -= 8

    elif volume_ratio > 180:

        priority -= 4

    # ========================================================
    # 接近60日高点扣分
    # ========================================================

    if drawdown < 3:

        priority -= 8

    elif drawdown < 5:

        priority -= 4

    # ========================================================
    # 相对市场强度奖励
    # ========================================================

    if relative_strength >= 3:

        priority += 6

    elif relative_strength >= 1:

        priority += 3

    # ========================================================
    # 限制范围
    # ========================================================

    priority = min(
        max(
            priority,
            0
        ),
        100
    )

    return round(
        priority,
        1
    )

# ============================================================
# V1.7 明日观察池
# ============================================================

def build_tomorrow_watchlist(df):

    watch = df[
        (
            df["猎手评分"] >= 70
        )
        &
        (
            df["分类"].isin(
                [
                    "🔴 重点观察",
                    "🔴 可以研究"
                ]
            )
        )
    ].copy()

    if watch.empty:

        return watch

    # ========================================================
    # 优先选择：
    # 评分高
    # 相对大盘强
    # 量能健康
    # ========================================================

    watch["明日观察分"] = (
        watch["猎手评分"] * 0.6
        +
        watch["相对市场%"].clip(
            -5,
            5
        ) * 4
        +
        watch["量能比%"].clip(
            70,
            160
        ) / 10
    )

    watch = watch.sort_values(
        "明日观察分",
        ascending=False
    )

    return watch.head(10)


# ============================================================
# V1.7 自动生成猎手结论
# ============================================================

def generate_hunter_conclusion(
    row,
    market_temperature
):

    score = row["猎手评分"]

    pct = row["涨跌幅%"]

    relative = row["相对市场%"]

    volume = row["量能比%"]

    rsi = row["RSI14"]

    if (
        market_temperature >= 70
        and score >= 80
        and relative >= 2
    ):

        return (
            "🔴 强势核心："
            "市场环境与板块强度同时占优，"
            "值得重点跟踪。"
        )

    if (
        score >= 70
        and 100 <= volume <= 180
        and 50 <= rsi <= 68
    ):

        return (
            "🔴 结构健康："
            "趋势、量能和位置相对协调，"
            "适合加入观察池。"
        )

    if pct >= 5 and rsi > 75:

        return (
            "🟠 注意追涨："
            "短线涨幅较大且RSI偏高，"
            "不建议仅因上涨而追入。"
        )

    if relative < -2:

        return (
            "🟢 弱于市场："
            "虽然可能出现反弹，"
            "但目前相对强度不足。"
        )

    return (
        "🟡 等待确认："
        "已有一定信号，但还需要后续走势确认。"
    )

# ============================================================
# 扫描市场
# ============================================================
def scan_market():

    all_codes = (
        list(INDICES.values())
        + [
            code
            for _, code in SECTORS
        ]
    )

    realtime = get_quotes_tencent(
        all_codes
    )

    # ========================================================
    # 指数
    # ========================================================

    index_data = {}
    index_errors = []

    for name, code in INDICES.items():

        item = realtime.get(code)

        if item:

            index_data[name] = item

        else:

            index_data[name] = None

            index_errors.append(
                f"{name}实时行情获取失败"
            )

    (
        market_status,
        market_reason,
        market_average_pct,
        positive_count,
        negative_count
    ) = analyze_market_environment(
        index_data
    )

    index_pct = [
        item["pct"]
        for item in index_data.values()
        if item is not None
    ]

    market_pct = (
        sum(index_pct) / len(index_pct)
        if index_pct
        else 0
    )

    # ========================================================
    # 板块扫描
    # ========================================================

    results = []
    errors = []

    for name, code in SECTORS:

        try:

            realtime_item = realtime.get(code)

            if not realtime_item:

                raise Exception(
                    "实时行情不存在"
                )

            history = get_history_tencent(
                code
            )

            result = analyze_sector(
                name,
                code,
                realtime_item,
                history,
                market_pct
            )

            # =================================================
            # V1.7 猎手评分
            # =================================================

            result["猎手评分"] = calculate_hunter_score(
                result
            )

            # =================================================
            # V1.7 自动分类
            # =================================================

            result["分类"] = classify_hunter(
                result
            )
            result["猎手优先级"] = calculate_hunter_priority(
               result
            )

            # =================================================
            # V1.7 猎手结论
            #
            # 暂时使用50作为市场温度
            # 第三段会接入真正的市场温度
            # =================================================


            results.append(
                result
            )

        except Exception as e:

            errors.append(
                f"{name}：{str(e)}"
            )

    # ========================================================
    # 判断是否有结果
    # ========================================================

    if not results:

        raise Exception(
            "所有板块分析失败"
        )

    # ========================================================
    # V1.7 市场温度
    # ========================================================

    market_temperature_data = calculate_market_temperature(
        index_data
    )

    market_temperature = market_temperature_data[
        "temperature"
    ]

    market_temperature_status = market_temperature_data[
        "status"
    ]

    # ========================================================
    # 转换DataFrame
    # ========================================================

    df = pd.DataFrame(
        results
    )

    # ========================================================
    # V1.7 根据真实市场温度生成猎手结论
    # ========================================================

    df["猎手结论"] = df.apply(
        lambda row: generate_hunter_conclusion(
            row,
            market_temperature
        ),
        axis=1
    )

    # ========================================================
    # V1.7
    # 按猎手评分排序
    # ========================================================
    df = df.sort_values(
         "猎手优先级",
         ascending=False
    ).reset_index(
        drop=True
    )

    # ========================================================
    # 排名
    # ========================================================

    df.insert(
        0,
        "排名",
        range(
            1,
            len(df) + 1
        )
    )

    # ========================================================
    # 明日观察池
    # ========================================================

    tomorrow_watchlist = build_tomorrow_watchlist(
        df
    )

    # ========================================================
    # 返回
    # ========================================================

    return (
        df,
        index_data,
        errors,
        index_errors,
        market_status,
        market_reason,
        market_pct,
        market_average_pct,
        positive_count,
        negative_count,
        tomorrow_watchlist
    )
# ============================================================
# 页面
# ============================================================

st.title("📈 复利人生 V1.6")

st.caption(
    "A股实时行情 · 全市场板块自动扫描 · 趋势 · 量能 · 强弱 · 风险"
)

st.info(
    """
**系统流程**

实时行情 → 市场环境 → 板块扫描 → 趋势分析
→ MACD + RSI + 量能 → 相对大盘强弱
→ 综合评分 → TOP 5 → 自动观察池 → 风险警戒
"""
)


# ============================================================
# 扫描按钮
# ============================================================

if st.button(
    "🔍 立即扫描 A股市场",
    type="primary",
    use_container_width=True
):

    st.session_state.pop(
        "scan_error",
        None
    )

    try:

        with st.spinner(
            "正在获取A股实时行情并扫描板块，请稍候..."
        ):

            result = scan_market()

        (
            df,
            index_data,
            errors,
            index_errors,
            market_status,
            market_reason,
            market_pct,
            market_average_pct,
            positive_count,
            negative_count,
            tomorrow_watchlist
        ) = result

        st.session_state["scan_df"] = df
        st.session_state["index_data"] = index_data
        st.session_state["scan_errors"] = errors
        st.session_state["index_errors"] = index_errors
        st.session_state["market_status"] = market_status
        st.session_state["market_reason"] = market_reason
        st.session_state["market_pct"] = market_pct
        st.session_state["market_average_pct"] = market_average_pct
        st.session_state["positive_count"] = positive_count
        st.session_state["negative_count"] = negative_count
        st.session_state["tomorrow_watchlist"] = tomorrow_watchlist        
        st.session_state["scan_time"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    except Exception:

        st.session_state[
            "scan_error"
        ] = traceback.format_exc()
# ============================================================
# V1.7 猎手工作台
# ============================================================

if "scan_df" in st.session_state:

    df = st.session_state["scan_df"]

    tomorrow_watchlist = st.session_state.get(
        "tomorrow_watchlist",
        pd.DataFrame()
    )

    market_average_pct = st.session_state.get(
        "market_average_pct",
        0
    )

    # --------------------------------------------------------
    # 市场温度
    # --------------------------------------------------------

    st.markdown("---")

    st.subheader(
        "🎯 复利人生 V1.7 · 猎手工作台"
    )

    # --------------------------------------------------------
    # 根据指数重新计算市场温度
    # --------------------------------------------------------

    index_data = st.session_state.get(
        "index_data",
        {}
    )

    temperature_data = calculate_market_temperature(
        index_data
    )

    temperature = temperature_data[
        "temperature"
    ]

    temperature_status = temperature_data[
        "status"
    ]

    temperature_description = temperature_data[
        "description"
    ]

    # --------------------------------------------------------
    # 三项核心指标
    # --------------------------------------------------------

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "🌡️ 市场温度",
            f"{temperature:.1f}"
        )

    with col2:

        st.metric(
            "市场状态",
            temperature_status
        )

    with col3:

        st.metric(
            "指数平均涨跌",
            f"{market_average_pct:+.2f}%"
        )

    # --------------------------------------------------------
    # 市场环境说明
    # --------------------------------------------------------

    if temperature >= 70:

        st.error(
            "🔴 进攻\n\n"
            + temperature_description
        )

    elif temperature >= 45:

        st.warning(
            "🟡 震荡\n\n"
            + temperature_description
        )

    else:

        st.success(
            "🟢 防守\n\n"
            + temperature_description
        )

    # ========================================================
    # 今日猎手 TOP 5
    # ========================================================

    st.markdown(
        "### 🔥 今日猎手 TOP 5"
    )

    top5 = df.head(5)

    for _, row in top5.iterrows():

        category = row.get(
            "分类",
            "🟡 等待确认"
        )

        score = row.get(
            "猎手评分",
            0
        )

        if category in [
            "🔴 重点观察",
            "🔴 可以研究"
        ]:

            st.error(
                f"🔴 **{row['板块']}**  "
                f"｜猎手评分 **{score:.0f}**  "
                f"｜{category}"
            )

        elif category == "🟡 等待确认":

            st.warning(
                f"🟡 **{row['板块']}**  "
                f"｜猎手评分 **{score:.0f}**  "
                f"｜{category}"
            )

        elif category in [
            "🟢 风险回避",
            "🟢 回避"
        ]:

            st.success(
                f"🟢 **{row['板块']}**  "
                f"｜猎手评分 **{score:.0f}**  "
                f"｜{category}"
            )

        else:

            st.info(
                f"**{row['板块']}**  "
                f"｜猎手评分 **{score:.0f}**  "
                f"｜{category}"
            )

    # ========================================================
    # 明日观察池
    # ========================================================

    st.markdown(
        "### 📅 明日观察池"
    )

    if tomorrow_watchlist.empty:

        st.info(
            "目前没有符合条件的板块。"
            "等待新的结构性机会。"
        )

    else:

        watch_columns = [
            "板块",
            "涨跌幅%",
            "猎手评分",
            "分类",
            "趋势",
            "相对市场%",
            "量能比%",
            "RSI14"
        ]

        available_columns = [
            col
            for col in watch_columns
            if col in tomorrow_watchlist.columns
        ]

        st.dataframe(
            tomorrow_watchlist[
                available_columns
            ],
            use_container_width=True,
            hide_index=True
        )

    # ========================================================
    # 猎手雷达
    # ========================================================

    st.markdown(
        "### 📡 A股板块猎手雷达"
    )

    radar_columns = [
        "排名",
        "板块",
        "涨跌幅%",
        "猎手评分",
        "猎手优先级",
        "分类",
        "趋势",
        "相对市场%",
        "量能比%",
        "RSI14",
        "追涨风险",
        "风险",
        "猎手结论"
    ]

    available_radar_columns = [
        col
        for col in radar_columns
        if col in df.columns
    ]

    st.dataframe(
        df[
            available_radar_columns
        ],
        use_container_width=True,
        hide_index=True
    )

# ============================================================
# 错误
# ============================================================

if "scan_error" in st.session_state:

    st.error("🔴 A股市场扫描失败")

    st.code(
        st.session_state["scan_error"],
        language="text"
    )


# ============================================================
# 成功后的页面
# ============================================================

if "scan_df" in st.session_state:

    df = st.session_state["scan_df"]
    index_data = st.session_state["index_data"]

    # ========================================================
    # 市场环境
    # ========================================================

    st.subheader("🌏 A股市场环境")

    col1, col2, col3, col4 = st.columns(4)

    for column, name in zip(
        [col1, col2, col3, col4],
        [
            "上证指数",
            "深证成指",
            "创业板指",
            "科创50"
        ]
    ):

        item = index_data.get(name)

        if item:

            column.metric(
                name,
                f"{item['price']:.2f}",
                f"{item['pct']:+.2f}%"
            )

        else:

            column.metric(
                name,
                "数据异常"
            )

    market_status = st.session_state[
        "market_status"
    ]

    market_reason = st.session_state[
        "market_reason"
    ]

    market_pct = st.session_state[
        "market_pct"
    ]

    positive_count = st.session_state[
        "positive_count"
    ]

    negative_count = st.session_state[
        "negative_count"
    ]

    st.markdown(
        f"""
### 当前市场状态：{market_status}

{market_reason}

**四大指数平均涨跌：**
{market_pct:+.2f}%

**上涨指数：** {positive_count} 个

**下跌指数：** {negative_count} 个
"""
    )

    st.caption(
        "最近扫描："
        + st.session_state["scan_time"]
    )

    st.divider()

    # ========================================================
    # TOP5
    # ========================================================

    st.subheader("🔥 今日机会 TOP 5")

    top5 = df.head(5)

    for _, row in top5.iterrows():

        rank = int(row["排名"])

        emoji = {
            1: "🥇",
            2: "🥈",
            3: "🥉"
        }.get(rank, "⭐")

        with st.container(border=True):

            st.markdown(
                f"""
### {emoji} #{rank} {row['板块']}

**机会评分：{row['机会评分']:.0f} / 100**

涨跌：**{row['涨跌幅%']:+.2f}%**

趋势：**{row['趋势']}**

相对市场：**{row['强弱']}**

量能：**{row['量能状态']}（{row['量能比%']:.0f}%）**

MACD：**{row['MACD状态']}**

RSI：**{row['RSI14']:.1f}**

60日回撤：**{row['60日回撤%']:.1f}%**

机会判断：**{row['级别']}**

追涨风险：**{row['追涨风险']}**
"""
            )

            if row["理由"]:

                st.success(
                    "入选理由：" + row["理由"]
                )

            if row["追涨条件"]:

                st.warning(
                    "追涨提示：" + row["追涨条件"]
                )

    st.divider()

    # ========================================================
    # 自动观察池
    # ========================================================

    st.subheader("👀 自动观察池")

    watchlist = df[
        df["机会评分"] >= 70
    ]

    if watchlist.empty:

        st.info(
            "当前没有板块达到70分观察标准。"
        )

    else:

        st.success(
            f"当前共有 {len(watchlist)} 个板块进入观察池。"
        )

        watch_display = watchlist[
            [
                "排名",
                "板块",
                "ETF",
                "涨跌幅%",
                "趋势",
                "强弱",
                "量能状态",
                "MACD状态",
                "RSI14",
                "机会评分",
                "级别",
                "追涨风险"
            ]
        ].copy()

        st.dataframe(
            watch_display,
            use_container_width=True,
            hide_index=True
        )

    # ========================================================
    # 全部排行榜
    # ========================================================

    st.subheader("📊 全部板块排行榜")

    display_df = df[
        [
            "排名",
            "板块",
            "ETF",
            "现价",
            "涨跌幅%",
            "趋势",
            "强弱",
            "量能比%",
            "量能状态",
            "RSI14",
            "MACD状态",
            "60日回撤%",
            "机会评分",
            "级别",
            "追涨风险",
            "风险"
        ]
    ].copy()

    numeric_columns = [
        "现价",
        "涨跌幅%",
        "量能比%",
        "RSI14",
        "60日回撤%",
        "机会评分"
    ]

    for column in numeric_columns:

        display_df[column] = display_df[
            column
        ].round(2)

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    # ========================================================
    # 风险警戒
    # ========================================================

    st.subheader("⚠️ 风险警戒")

    danger = df[
        df["风险"].isin(
            [
                "🟡 注意",
                "🔴 警戒"
            ]
        )
    ]

    if danger.empty:

        st.success(
            "当前没有明显风险警戒。"
        )

    else:

        for _, row in danger.iterrows():

            text = (
                f"{row['板块']}｜"
                f"{row['风险']}｜"
                f"{row['风险条件']}"
            )

            if row["风险"] == "🔴 警戒":

                st.error(text)

            else:

                st.warning(text)

    # ========================================================
    # 追涨警戒
    # ========================================================

    st.subheader(
        "🚨 强势但不宜盲目追涨"
    )

    chase_df = df[
        df["追涨风险"].isin(
            [
                "🔴 强势但追涨风险高",
                "🟡 强势，注意追涨"
            ]
        )
    ]

    if chase_df.empty:

        st.success(
            "当前没有明显追涨警报。"
        )

    else:

        for _, row in chase_df.iterrows():

            st.warning(
                f"{row['板块']}｜"
                f"{row['涨跌幅%']:+.2f}%｜"
                f"{row['追涨风险']}｜"
                f"{row['追涨条件']}"
            )

    # ========================================================
    # 数据异常
    # ========================================================

    errors = st.session_state.get(
        "scan_errors",
        []
    )

    index_errors = st.session_state.get(
        "index_errors",
        []
    )

    if errors or index_errors:

        st.subheader(
            "⚠️ 数据异常日志"
        )

        with st.expander(
            "点击查看异常"
        ):

            for error in index_errors:
                st.write("• " + error)

            for error in errors:
                st.write("• " + error)


else:

    st.info(
        "点击「🔍 立即扫描 A股市场」开始扫描。"
    )

    st.markdown(
        """
### V1.6

**四大指数**

↓

**30+板块**

↓

**实时涨跌**

↓

**MA20 / MA60**

↓

**MACD**

↓

**RSI**

↓

**量能**

↓

**相对大盘强弱**

↓

**机会评分**

↓

**TOP 5**

↓

**自动观察池**

↓

**风险警戒**
"""
    )


# ============================================================
# 页脚
# ============================================================

st.divider()

st.caption(
    "复利人生 V1.6 · "
    "行情扫描仅用于辅助研究，不构成投资建议。"
)
