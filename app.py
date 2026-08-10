import streamlit as st
import requests
import pandas as pd
import time
import traceback

# ============================================================
# 复利人生 V1.2
# A股实时行情双数据源测试版
#
# 数据源：
# 1. 腾讯财经
# 2. 新浪财经
#
# 逻辑：
# 腾讯成功 -> 使用腾讯
# 腾讯失败 -> 自动切换新浪
# 腾讯 + 新浪都失败 -> 显示完整错误
# ============================================================

st.set_page_config(
    page_title="复利人生 V1.2",
    page_icon="📈",
    layout="wide"
)

# ============================================================
# 基础设置
# ============================================================

TIMEOUT = 8

# 我们暂时测试5个板块ETF
SECTORS = [
    ("半导体", "512480"),
    ("人工智能", "159819"),
    ("军工", "512660"),
    ("电力", "159611"),
    ("有色金属", "512400"),
]

# 上证指数
INDEX_CODE = "000001"


# ============================================================
# 股票代码转换
# ============================================================

def market_code(code):

    code = str(code)

    # 上海
    if code.startswith(("5", "6", "9")):
        return "sh" + code

    # 深圳
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

        # 找到：
        # v_sh600000="..."
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

            values = right.rstrip('"').split("~")

            if len(values) < 6:
                continue

            name = values[1]

            price = float(
                values[3]
            )

            yesterday = float(
                values[4]
            )

            change = float(
                values[5]
            )

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
                "pct": pct,
                "source": "腾讯财经"
            }

        except Exception:

            continue

    if not result:

        raise Exception(
            "腾讯行情接口没有解析出有效数据"
        )

    return result


# ============================================================
# 新浪实时行情
# ============================================================

def get_quotes_sina(codes):

    symbols = ",".join(
        market_code(code)
        for code in codes
    )

    url = (
        "https://hq.sinajs.cn/list="
        + symbols
    )

    response = requests.get(
        url,
        timeout=TIMEOUT,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/"
        }
    )

    response.raise_for_status()

    text = response.text

    if not text:
        raise Exception(
            "新浪行情接口返回空内容"
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
                .replace("var hq_str_", "")
                .strip()
            )

            values = right.rstrip('"').split(",")

            if len(values) < 4:
                continue

            name = values[0]

            # 新浪：
            # 1 开盘
            # 2 昨收
            # 3 当前价

            yesterday = float(
                values[2]
            )

            price = float(
                values[3]
            )

            if yesterday != 0:

                pct = (
                    (price - yesterday)
                    / yesterday
                    * 100
                )

            else:

                pct = 0

            change = (
                price - yesterday
            )

            code = symbol[-6:]

            result[code] = {
                "name": name,
                "price": price,
                "change": change,
                "pct": pct,
                "source": "新浪财经"
            }

        except Exception:

            continue

    if not result:

        raise Exception(
            "新浪行情接口没有解析出有效数据"
        )

    return result


# ============================================================
# 双数据源自动切换
# ============================================================

def get_quotes(codes):

    errors = []

    # --------------------------------------------------------
    # 第一数据源：腾讯
    # --------------------------------------------------------

    try:

        start = time.time()

        result = get_quotes_tencent(
            codes
        )

        elapsed = (
            time.time() - start
        )

        return (
            result,
            "腾讯财经",
            elapsed,
            errors
        )

    except Exception as e:

        errors.append(
            "腾讯财经失败："
            + str(e)
        )


    # --------------------------------------------------------
    # 第二数据源：新浪
    # --------------------------------------------------------

    try:

        start = time.time()

        result = get_quotes_sina(
            codes
        )

        elapsed = (
            time.time() - start
        )

        return (
            result,
            "新浪财经",
            elapsed,
            errors
        )

    except Exception as e:

        errors.append(
            "新浪财经失败："
            + str(e)
        )


    # --------------------------------------------------------
    # 两个数据源全部失败
    # --------------------------------------------------------

    raise Exception(
        "\n".join(errors)
    )


# ============================================================
# 测试市场行情
# ============================================================

def scan_market():

    codes = [
        INDEX_CODE
    ]

    for name, code in SECTORS:

        codes.append(code)

    return get_quotes(
        codes
    )


# ============================================================
# 页面标题
# ============================================================

st.title(
    "📈 复利人生 V1.2"
)

st.caption(
    "A股实时行情双数据源测试版"
)

st.divider()


# ============================================================
# 数据源说明
# ============================================================

st.info(
    """
当前行情引擎：

① 腾讯财经
↓
如果失败
↓
② 新浪财经
↓
如果两个都失败
↓
显示完整错误日志

本版本暂时不使用东方财富。
"""
)


# ============================================================
# 扫描按钮
# ============================================================

if st.button(
    "🔄 获取 A股实时行情",
    type="primary"
):

    # 清除旧结果

    st.session_state.pop(
        "market_data",
        None
    )

    st.session_state.pop(
        "market_error",
        None
    )


    try:

        with st.spinner(
            "正在连接 A股行情数据源..."
        ):

            (
                data,
                source,
                elapsed,
                errors
            ) = scan_market()


        st.session_state[
            "market_data"
        ] = data

        st.session_state[
            "market_source"
        ] = source

        st.session_state[
            "market_elapsed"
        ] = elapsed

        st.session_state[
            "market_errors"
        ] = errors


    except Exception as e:

        st.session_state[
            "market_error"
        ] = traceback.format_exc()


# ============================================================
# 显示错误
# ============================================================

if "market_error" in st.session_state:

    st.error(
        "🔴 A股行情连接失败"
    )

    st.code(
        st.session_state[
            "market_error"
        ],
        language="text"
    )

    st.warning(
        "腾讯和新浪两个数据源均未成功。"
    )


# ============================================================
# 显示行情
# ============================================================

if "market_data" in st.session_state:

    data = st.session_state[
        "market_data"
    ]

    source = st.session_state[
        "market_source"
    ]

    elapsed = st.session_state[
        "market_elapsed"
    ]


    st.success(
        "🟢 A股行情连接成功"
    )


    # --------------------------------------------------------
    # 数据源状态
    # --------------------------------------------------------

    col1, col2, col3 = st.columns(3)


    col1.metric(
        "当前数据源",
        source
    )


    col2.metric(
        "返回数据",
        len(data)
    )


    col3.metric(
        "响应时间",
        f"{elapsed:.2f} 秒"
    )


    st.divider()


    # --------------------------------------------------------
    # 上证指数
    # --------------------------------------------------------

    index = data.get(
        INDEX_CODE
    )


    if index:

        st.subheader(
            "🇨🇳 上证指数"
        )


        a, b, c = st.columns(3)


        a.metric(
            "指数",
            f"{index['price']:.2f}"
        )


        b.metric(
            "涨跌",
            f"{index['change']:+.2f}"
        )


        c.metric(
            "涨跌幅",
            f"{index['pct']:+.2f}%"
        )


    st.divider()


    # --------------------------------------------------------
    # 板块行情
    # --------------------------------------------------------

    st.subheader(
        "🔥 板块实时行情"
    )


    rows = []


    for name, code in SECTORS:

        item = data.get(code)


        if item:

            rows.append({

                "板块": name,

                "ETF代码": code,

                "当前价格": item[
                    "price"
                ],

                "涨跌": item[
                    "change"
                ],

                "涨跌幅%": item[
                    "pct"
                ],

                "数据源": item[
                    "source"
                ]

            })

        else:

            rows.append({

                "板块": name,

                "ETF代码": code,

                "当前价格": None,

                "涨跌": None,

                "涨跌幅%": None,

                "数据源": "未获取"

            })


    if rows:

        df = pd.DataFrame(
            rows
        )

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )


    # --------------------------------------------------------
    # 如果发生了数据源切换
    # --------------------------------------------------------

    errors = st.session_state.get(
        "market_errors",
        []
    )


    if errors:

        with st.expander(
            "⚠️ 数据源切换记录"
        ):

            for error in errors:

                st.write(
                    "• " + error
                )


st.divider()


st.caption(
    "复利人生 V1.2｜当前任务：验证云端 A股实时行情"
)
