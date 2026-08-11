import streamlit as st
import requests
import pandas as pd
import numpy as np
import traceback
from datetime import datetime

# ============================================================
# 复利人生 V1.6
# A股全市场板块自动扫描系统
#
# 核心：
# 1. 腾讯实时行情
# 2. 四大指数
# 3. 30+板块观察池
# 4. 趋势分析
# 5. MACD
# 6. RSI
# 7. 量能
# 8. 相对市场强弱
# 9. 机会评分
# 10. TOP5
# 11. 追涨风险
# 12. 风险警戒
# ============================================================


# ============================================================
# 页面配置
# ============================================================

st.set_page_config(
    page_title="复利人生 V1.6",
    page_icon="📈",
    layout="wide"
)


TIMEOUT = 10


# ============================================================
# 板块观察池
#
# ETF代码尽量选择流动性较好的宽基/行业ETF。
# 后续还可以继续扩充。
# ============================================================

SECTORS = [

    # --------------------------------------------------------
    # 科技 / AI
    # --------------------------------------------------------

    ("半导体", "512480"),

    ("人工智能", "159819"),

    ("科创芯片", "588200"),

    ("通信", "515880"),

    ("计算机", "512720"),

    ("机器人", "562500"),

    ("传媒", "512980"),


    # --------------------------------------------------------
    # 军工
    # --------------------------------------------------------

    ("军工", "512660"),


    # --------------------------------------------------------
    # 电力 / 公用事业
    # --------------------------------------------------------

    ("电力", "159611"),

    ("公用事业", "159301"),


    # --------------------------------------------------------
    # 有色 / 资源
    # --------------------------------------------------------

    ("有色金属", "512400"),

    ("稀土", "159608"),

    ("黄金", "518880"),

    ("煤炭", "515220"),

    ("钢铁", "515210"),

    ("石油", "561360"),


    # --------------------------------------------------------
    # 化工
    # --------------------------------------------------------

    ("化工", "516020"),

    ("基础化工", "516020"),


    # --------------------------------------------------------
    # 新能源
    # --------------------------------------------------------

    ("新能源", "516160"),

    ("光伏", "515790"),

    ("新能源车", "515030"),


    # --------------------------------------------------------
    # 医药
    # --------------------------------------------------------

    ("医药", "512010"),

    ("创新药", "159992"),


    # --------------------------------------------------------
    # 金融
    # --------------------------------------------------------

    ("证券", "512880"),

    ("银行", "512800"),

    ("金融科技", "159851"),


    # --------------------------------------------------------
    # 消费
    # --------------------------------------------------------

    ("消费", "159928"),

    ("食品饮料", "515170"),

    ("白酒", "512690"),


    # --------------------------------------------------------
    # 制造 / 汽车
    # --------------------------------------------------------

    ("汽车", "516110"),

    ("机械", "516960"),


    # --------------------------------------------------------
    # 红利 / 宽基
    # --------------------------------------------------------

    ("红利", "515180"),

    ("高股息", "563180"),

    ("沪深300", "510300"),

    ("中证1000", "512100"),

    ("创业板", "159915"),

]


# ============================================================
# 四大市场指数
#
# 这里是本次重点修复。
#
# 不能再使用简单的：
#
# 000001 -> sz000001
#
# 因为：
#
# sh000001 = 上证指数
# sz000001 = 平安银行
#
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


    # ========================================================
    # 指数专用映射
    # ========================================================

    INDEX_MARKET = {

        "000001": "sh000001",

        "399001": "sz399001",

        "399006": "sz399006",

        "000688": "sh000688",

    }


    if code in INDEX_MARKET:

        return INDEX_MARKET[code]


    # ========================================================
    # 上海市场
    #
    # 5开头：ETF
    # 6开头：股票
    # 9开头：部分上海证券
    # ========================================================

    if code.startswith(
        (
            "5",
            "6",
            "9"
        )
    ):

        return "sh" + code


    # ========================================================
    # 深圳市场
    # ========================================================

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


            # =================================================
            # 腾讯行情字段至少需要到32
            # =================================================

            if len(values) <= 32:

                continue


            name = values[1]


            # 当前价格
            price = float(
                values[3]
            )


            # 昨收
            yesterday = float(
                values[4]
            )


            # 今开
            today_open = float(
                values[5]
            )


            # =================================================
            # 涨跌
            #
            # 不再错误使用 values[5]
            # =================================================

            change = (
                price - yesterday
            )


            # =================================================
            # 涨跌幅
            #
            # 腾讯接口直接提供
            # =================================================

            try:

                pct = float(
                    values[32]
                )

            except Exception:

                if yesterday != 0:

                    pct = (
                        (
                            price
                            - yesterday
                        )
                        / yesterday
                        * 100
                    )

                else:

                    pct = 0


            code = symbol[-6:]


            result[code] = {

                "name": name,

                "price": price,

                "yesterday": yesterday,

                "open": today_open,

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


    data_block = data.get(
        "data"
    )


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

        rows = stock_data[
            "qfqday"
        ]


    elif "day" in stock_data:

        rows = stock_data[
            "day"
        ]


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

                "open": float(
                    row[1]
                ),

                "close": float(
                    row[2]
                ),

                "high": float(
                    row[3]
                ),

                "low": float(
                    row[4]
                ),

                "volume": float(
                    row[5]
                )

            })


        except Exception:

            continue


    if len(result) < 60:

        raise Exception(
            f"{code} 有效历史K线不足60根"
        )


    return pd.DataFrame(
        result
    )


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    close,
    period=14
):

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
        /
        avg_loss.replace(
            0,
            np.nan
        )
    )


    rsi = (
        100
        -
        100 / (1 + rs)
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


    dif = (
        ema12 - ema26
    )


    dea = dif.ewm(
        span=9,
        adjust=False
    ).mean()


    hist = (
        dif - dea
    )


    return (
        dif,
        dea,
        hist
    )


# ============================================================
# 板块分析
# ============================================================

def analyze_sector(
    name,
    code,
    realtime,
    history,
    market_pct
):

    close = history[
        "close"
    ]


    volume = history[
        "volume"
    ]


    price = realtime[
        "price"
    ]


    # ========================================================
    # MA20 / MA60
    # ========================================================

    ma20 = float(
        close
        .tail(20)
        .mean()
    )


    ma60 = float(
        close
        .tail(60)
        .mean()
    )


    # ========================================================
    # 60日高点
    # ========================================================

    high60 = float(
        history[
            "high"
        ]
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

    # ========================================================
    # RSI
    # ========================================================

    rsi_series = (
        calculate_rsi(
            close
        )
    )


    rsi = float(
        rsi_series.iloc[-1]
    )


    # ========================================================
    # MACD
    # ========================================================

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


    # ========================================================
    # 量能
    # ========================================================

    avg_volume = float(
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


    # ========================================================
    # 相对市场强弱
    # ========================================================

    relative_strength = (
        realtime["pct"]
        - market_pct
    )


    # ========================================================
    # 趋势
    # ========================================================

    if (
        price > ma20
        and ma20 > ma60
    ):

        trend = "强势上升"


    elif price > ma20:

        trend = "短线转强"


    elif (
        price < ma20
        and ma20 > ma60
    ):

        trend = "回调"


    else:

        trend = "偏弱"


    # ========================================================
    # MACD状态
    # ========================================================

    if (
        macd_hist > 0
        and macd_hist
        > previous_macd_hist
    ):

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
    # 相对市场
    # ========================================================

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


    # ========================================================
    # 趋势 25
    # ========================================================

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


    # ========================================================
    # 相对强度 20
    # ========================================================

    if relative_strength >= 3:

        score += 20

        reasons.append(
            "明显强于市场"
        )


    elif relative_strength >= 1:

        score += 15

        reasons.append(
            "强于市场"
        )


    elif relative_strength >= 0:

        score += 10


    elif relative_strength >= -2:

        score += 5

        warnings.append(
            "略弱于市场"
        )


    else:

        score += 2

        warnings.append(
            "明显弱于市场"
        )


    # ========================================================
    # 量能 20
    # ========================================================

    if (
        120
        <= volume_ratio
        <= 180
    ):

        score += 20

        reasons.append(
            "健康放量"
        )


    elif (
        100
        <= volume_ratio
        < 120
    ):

        score += 15


    elif volume_ratio > 180:

        score += 12

        warnings.append(
            "量能过高"
        )


    elif volume_ratio >= 70:

        score += 8


    else:

        score += 4

        warnings.append(
            "成交量偏低"
        )


    # ========================================================
    # MACD 15
    # ========================================================

    if (
        macd_hist > 0
        and macd_hist
        > previous_macd_hist
    ):

        score += 15

        reasons.append(
            "MACD动能增强"
        )


    elif macd_hist > 0:

        score += 11

        reasons.append(
            "MACD多头"
        )


    else:

        score += 3

        warnings.append(
            "MACD偏弱"
        )


    # ========================================================
    # RSI 10
    # ========================================================

    if (
        50
        <= rsi
        <= 68
    ):

        score += 10

        reasons.append(
            "RSI健康"
        )


    elif (
        45
        <= rsi
        < 50
    ):

        score += 7


    elif (
        68
        < rsi
        <= 75
    ):

        score += 6

        warnings.append(
            "RSI偏高"
        )


    elif rsi > 75:

        score += 3

        warnings.append(
            "RSI过热"
        )


    else:

        score += 3

        warnings.append(
            "RSI偏弱"
        )


    # ========================================================
    # 回撤 10
    # ========================================================

    if (
        5
        <= drawdown
        <= 20
    ):

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


    # ========================================================
    # 限制评分
    # ========================================================

    score = float(
        min(
            max(
                score,
                0
            ),
            100
        )
    )


    # ========================================================
    # 基础等级
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
    # 追涨风险
    #
    # 重点解决：
    #
    # “涨得最多 ≠ 最值得买”
    # ========================================================

    chase_flags = []


    if rsi > 75:

        chase_flags.append(
            "RSI过热"
        )


    if volume_ratio > 200:

        chase_flags.append(
            "异常放量"
        )


    if drawdown < 3:

        chase_flags.append(
            "接近60日高点"
        )


    if realtime["pct"] >= 5:

        chase_flags.append(
            "当日涨幅较大"
        )


    # ========================================================
    # 追涨状态
    # ========================================================

    if len(chase_flags) >= 2:

        chase_status = (
            "🔴 强势但追涨风险高"
        )


    elif len(chase_flags) == 1:

        chase_status = (
            "🟡 强势，注意追涨"
        )


    else:

        chase_status = (
            "🟢 暂无明显追涨风险"
        )


    # ========================================================
    # 风险条件
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
            "明显弱于市场"
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

        "涨跌幅%": realtime[
            "pct"
        ],

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

        "追涨条件": "、".join(
            chase_flags
        ),

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
# 第一段结束
#
# 下一段直接接在这里。
# ==========================================================
# ============================================================
# 复利人生 V1.6 第二段
# 市场扫描 + TOP5 + 页面
# ============================================================


# ============================================================
# 综合市场环境
# ============================================================

def analyze_market_environment(index_data):

    valid = []

    for name, data in index_data.items():

        if data is None:
            continue

        valid.append({
            "name": name,
            "pct": data["pct"]
        })


    if not valid:

        return (
            "🔴 数据异常",
            "主要指数均无法获取",
            0,
            0,
            0
        )


    average_pct = (
        sum(
            item["pct"]
            for item in valid
        )
        / len(valid)
    )


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


    # ========================================================
    # 市场状态
    # ========================================================

    if (
        average_pct >= 1
        and positive >= total * 0.75
    ):

        status = "🟢 强势"

        reason = (
            "主要指数整体上涨，"
            "市场风险偏好较强。"
        )


    elif (
        average_pct <= -1
        and negative >= total * 0.75
    ):

        status = "🔴 弱势"

        reason = (
            "主要指数整体走弱，"
            "市场风险偏好下降。"
        )


    elif (
        average_pct > 0.3
        and positive > negative
    ):

        status = "🟢 偏强"

        reason = (
            "主要指数多数上涨，"
            "市场环境偏积极。"
        )


    elif (
        average_pct < -0.3
        and negative > positive
    ):

        status = "🟠 偏弱"

        reason = (
            "主要指数多数下跌，"
            "市场环境偏谨慎。"
        )


    else:

        status = "🟡 震荡"

        reason = (
            "主要指数涨跌分化，"
            "暂未形成明确市场方向。"
        )


    return (
        status,
        reason,
        average_pct,
        positive,
        negative
    )


# ============================================================
# 扫描全部板块
# ============================================================

def scan_market():

    # ========================================================
    # 所有指数代码
    # ========================================================

    index_codes = list(
        INDICES.values()
    )


    # ========================================================
    # 所有板块代码
    # ========================================================

    sector_codes = [
        code
        for name, code
        in SECTORS
    ]


    # ========================================================
    # 一次请求实时行情
    # ========================================================

    all_codes = (
        index_codes
        + sector_codes
    )


    realtime = get_quotes_tencent(
        all_codes
    )


    # ========================================================
    # 解析四大指数
    # ========================================================

    index_data = {}

    index_errors = []


    for name, code in INDICES.items():

        item = realtime.get(
            code
        )


        if item:

            index_data[name] = item

        else:

            index_data[name] = None

            index_errors.append(
                f"{name}实时行情获取失败"
            )


    # ========================================================
    # 综合市场环境
    # ========================================================

    (
        market_status,
        market_reason,
        market_average_pct,
        positive_count,
        negative_count
    ) = analyze_market_environment(
        index_data
    )


    # ========================================================
    # 市场基准
    #
    # 使用四大指数平均涨跌幅。
    # ========================================================

    index_pct = [

        item["pct"]

        for item
        in index_data.values()

        if item is not None
    ]


    if index_pct:

        market_pct = (
            sum(index_pct)
            / len(index_pct)
        )

    else:

        market_pct = 0


    # ========================================================
    # 扫描板块
    # ========================================================

    results = []

    errors = []


    for name, code in SECTORS:

        try:

            realtime_item = realtime.get(
                code
            )


            if not realtime_item:

                raise Exception(
                    "实时行情不存在"
                )


            # ------------------------------------------------
            # 获取历史K线
            # ------------------------------------------------

            history = (
                get_history_tencent(
                    code
                )
            )


            # ------------------------------------------------
            # 技术分析
            # ------------------------------------------------

            result = analyze_sector(

                name=name,

                code=code,

                realtime=realtime_item,

                history=history,

                market_pct=market_pct

            )


            results.append(
                result
            )


        except Exception as e:

            errors.append(
                f"{name}：{str(e)}"
            )


    # ========================================================
    # 如果全部失败
    # ========================================================

    if not results:

        raise Exception(
            "所有板块分析失败"
        )


    # ========================================================
    # DataFrame
    # ========================================================

    df = pd.DataFrame(
        results
    )


    # ========================================================
    # 排序
    # ========================================================

    df = df.sort_values(
        "机会评分",
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

        negative_count

    )


# ============================================================
# 页面标题
# ============================================================

st.title(
    "📈 复利人生 V1.6"
)


st.caption(
    "A股全市场板块自动扫描 · 趋势 · 量能 · 强弱 · 风险"
)


st.info(
    """
### 复利人生 V1.6

实时行情
↓
四大指数判断市场环境
↓
30+行业 / 主题自动扫描
↓
趋势 + MACD + RSI + 量能
↓
相对大盘强弱
↓
综合机会评分
↓
TOP 5重点观察
↓
风险 / 追涨警戒

系统的作用是帮助发现机会，
最终交易仍由投资者自己决定。
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

    # --------------------------------------------------------
    # 清除上次错误
    # --------------------------------------------------------

    st.session_state.pop(
        "scan_error",
        None
    )


    try:

        with st.spinner(
            "正在获取A股实时行情并扫描全部板块，请稍候..."
        ):

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
                negative_count

            ) = scan_market()


        # ====================================================
        # 保存结果
        # ====================================================

        st.session_state[
            "scan_df"
        ] = df


        st.session_state[
            "index_data"
        ] = index_data


        st.session_state[
            "scan_errors"
        ] = errors


        st.session_state[
            "index_errors"
        ] = index_errors


        st.session_state[
            "market_status"
        ] = market_status


        st.session_state[
            "market_reason"
        ] = market_reason


        st.session_state[
            "market_pct"
        ] = market_pct


        st.session_state[
            "market_average_pct"
        ] = market_average_pct


        st.session_state[
            "positive_count"
        ] = positive_count


        st.session_state[
            "negative_count"
        ] = negative_count


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
# 扫描错误
# ============================================================

if "scan_error" in st.session_state:

    st.error(
        "🔴 A股市场扫描失败"
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


    index_data = st.session_state[
        "index_data"
    ]


    # ========================================================
    # 一、市场环境
    # ========================================================

    st.subheader(
        "🌏 A股市场环境"
    )


    col1, col2, col3, col4 = (
        st.columns(4)
    )


    # --------------------------------------------------------
    # 上证指数
    # --------------------------------------------------------

    shanghai = index_data.get(
        "上证指数"
    )


    if shanghai:

        col1.metric(

            "上证指数",

            f"{shanghai['price']:.2f}",

            f"{shanghai['pct']:+.2f}%"

        )

    else:

        col1.metric(
            "上证指数",
            "数据异常"
        )


    # --------------------------------------------------------
    # 深证成指
    # --------------------------------------------------------

    shenzhen = index_data.get(
        "深证成指"
    )


    if shenzhen:

        col2.metric(

            "深证成指",

            f"{shenzhen['price']:.2f}",

            f"{shenzhen['pct']:+.2f}%"

        )

    else:

        col2.metric(
            "深证成指",
            "数据异常"
        )


    # --------------------------------------------------------
    # 创业板指
    # --------------------------------------------------------

    chinext = index_data.get(
        "创业板指"
    )


    if chinext:

        col3.metric(

            "创业板指",

            f"{chinext['price']:.2f}",

            f"{chinext['pct']:+.2f}%"

        )

    else:

        col3.metric(
            "创业板指",
            "数据异常"
        )


    # --------------------------------------------------------
    # 科创50
    # --------------------------------------------------------

    star50 = index_data.get(
        "科创50"
    )


    if star50:

        col4.metric(

            "科创50",

            f"{star50['price']:.2f}",

            f"{star50['pct']:+.2f}%"

        )

    else:

        col4.metric(
            "科创50",
            "数据异常"
        )


    # ========================================================
    # 市场综合状态
    # ========================================================

    market_status = (
        st.session_state[
            "market_status"
        ]
    )


    market_reason = (
        st.session_state[
            "market_reason"
        ]
    )


    market_pct = (
        st.session_state[
            "market_pct"
        ]
    )


    positive_count = (
        st.session_state[
            "positive_count"
        ]
    )


    negative_count = (
        st.session_state[
            "negative_count"
        ]
    )


    st.markdown(
        f"""
### 当前市场状态：{market_status}

{market_reason}

**四大指数平均涨跌：**
{market_pct:+.2f}%

**上涨指数：**
{positive_count} 个

**下跌指数：**
{negative_count} 个
"""
    )


    st.caption(
        "最近一次扫描："
        + st.session_state[
            "scan_time"
        ]
    )


    st.divider()


    # ========================================================
    # 二、TOP 5
    # ========================================================

    st.subheader(
        "🔥 今日机会 TOP 5"
    )


    top5 = df.head(5)


    for index, row in top5.iterrows():

        rank = int(
            row["排名"]
        )


        # ----------------------------------------------------
        # TOP5卡片
        # ----------------------------------------------------

        with st.container(
            border=True
        ):

            if rank == 1:

                title = "🥇"

            elif rank == 2:

                title = "🥈"

            elif rank == 3:

                title = "🥉"

            else:

                title = "⭐"


            st.markdown(
                f"""
## {title} #{rank} {row['板块']}

**机会评分：{row['机会评分']:.0f} / 100**

**当前涨跌：**
{row['涨跌幅%']:+.2f}%

**趋势：**
{row['趋势']}

**相对市场：**
{row['强弱']}

**量能：**
{row['量能状态']}（{row['量能比%']:.0f}%）

**MACD：**
{row['MACD状态']}

**RSI：**
{row['RSI14']:.1f}

**60日回撤：**
{row['60日回撤%']:.1f}%

**机会判断：**
{row['级别']}

**追涨风险：**
{row['追涨风险']}
"""
            )


            # ------------------------------------------------
            # 入选理由
            # ------------------------------------------------

            if row["理由"]:

                st.success(
                    "入选理由："
                    + row["理由"]
                )


            # ------------------------------------------------
            # 风险提示
            # ------------------------------------------------

            if row["追涨条件"]:

                st.warning(
                    "追涨提示："
                    + row["追涨条件"]
                )


    st.divider()


    # ========================================================
    # 三、自动观察池
    # ========================================================

    st.subheader(
        "👀 自动观察池"
    )


    watchlist = df[
        df["机会评分"] >= 70
    ]


    if len(watchlist) == 0:

        st.info(
            "当前没有板块达到70分观察标准。"
        )


        st.markdown(
            """
### 当前策略倾向

**等待，而不是强行交易。**

没有符合条件的板块，
系统不会为了凑数量而制造机会。
"""
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
    # 四、完整排行榜
    # ========================================================

    st.subheader(
        "📊 全部板块排行榜"
    )


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


    # ========================================================
    # 数值格式
    # ========================================================

    display_df[
        "现价"
    ] = display_df[
        "现价"
    ].round(3)


    display_df[
        "涨跌幅%"
    ] = display_df[
        "涨跌幅%"
    ].round(2)


    display_df[
        "量能比%"
    ] = display_df[
        "量能比%"
    ].round(1)


    display_df[
        "RSI14"
    ] = display_df[
        "RSI14"
    ].round(1)


    display_df[
        "60日回撤%"
    ] = display_df[
        "60日回撤%"
    ].round(1)


    display_df[
        "机会评分"
    ] = display_df[
        "机会评分"
    ].round(0)


    st.dataframe(

        display_df,

        use_container_width=True,

        hide_index=True

    )


    # ========================================================
    # 五、风险警戒
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
            "当前没有明显风险警戒。"
        )


    else:

        for _, row in danger.iterrows():

            if row["风险"] == "🔴 警戒":

                st.error(

                    f"{row['板块']}｜"
                    f"{row['风险']}｜"
                    f"{row['风险条件']}"

                )

            else:

                st.warning(

                    f"{row['板块']}｜"
                    f"{row['风险']}｜"
                    f"{row['风险条件']}"

                )


    # ========================================================
    # 六、强势但不宜追涨
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


    if len(chase_df) == 0:

        st.success(
            "当前没有明显的追涨警报。"
        )


    else:

        for _, row in chase_df.iterrows():

            st.warning(

                f"**{row['板块']}**｜"
                f"{row['涨跌幅%']:+.2f}%｜"
                f"{row['追涨风险']}｜"
                f"{row['追涨条件']}"

            )


    # ========================================================
    # 七、数据异常日志
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

                st.write(
                    "• " + error
                )


            for error in errors:

                st.write(
                    "• " + error
                )


# ============================================================
# 初始页面
# ============================================================

else:

    st.info(
        "点击「🔍 立即扫描 A股市场」开始扫描。"
    )


    st.markdown(
        """
### V1.6 工作流程

**实时行情**

↓

**四大指数判断市场环境**

↓

**30+板块自动扫描**

↓

**趋势 + 量能 + MACD + RSI**

↓

**相对大盘强弱**

↓

**机会评分**

↓

**TOP 5**

↓

**自动观察池**

↓

**风险 / 追涨警戒**
"""
    )


# ============================================================
# 页脚
# ============================================================

st.divider()


st.caption(
    "复利人生 V1.6 · "
    "自动扫描只是辅助工具，不构成投资建议。"
)
