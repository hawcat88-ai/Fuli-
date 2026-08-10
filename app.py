import streamlit as st
import requests
import pandas as pd
import traceback

st.set_page_config(
    page_title="复利人生 V1.1",
    page_icon="📈",
    layout="wide"
)

st.title("📈 复利人生 V1.1")
st.caption("A股真实行情连接测试版")

# =========================
# 基础配置
# =========================

TIMEOUT = 10

SECTORS = [
    ("半导体", "512480"),
    ("人工智能", "159819"),
    ("军工", "512660"),
    ("电力", "159611"),
    ("有色金属", "512400"),
]


# =========================
# 判断市场代码
# =========================

def get_secid(code):

    if code.startswith(("5", "6")):
        return "1." + code

    return "0." + code


# =========================
# 获取东方财富实时行情
# =========================

def get_realtime_quotes(codes):

    secids = ",".join(
        get_secid(code)
        for code in codes
    )

    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get"
        "?fltt=2"
        "&invt=2"
        "&fields=f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18"
        "&secids="
        + secids
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

    if not data:
        raise Exception(
            "东方财富服务器返回空数据"
        )

    market_data = data.get("data")

    if not market_data:
        raise Exception(
            "东方财富返回结果中没有 data"
        )

    diff = market_data.get("diff")

    if not diff:
        raise Exception(
            "东方财富返回结果中没有 diff"
        )

    if isinstance(diff, dict):
        rows = list(diff.values())
    else:
        rows = diff

    result = {}

    for item in rows:

        code = str(
            item.get("f12", "")
        )

        if not code:
            continue

        result[code] = {
            "name": item.get(
                "f14",
                code
            ),
            "price": item.get(
                "f2",
                0
            ),
            "change": item.get(
                "f3",
                0
            )
        }

    return result


# =========================
# 测试行情连接
# =========================

def test_market():

    codes = [
        "000001",
        "512480",
        "159819",
        "512660",
        "159611",
        "512400"
    ]

    return get_realtime_quotes(
        codes
    )


# =========================
# 页面按钮
# =========================

if st.button(
    "🔄 测试 A股实时行情",
    type="primary"
):

    st.session_state.pop(
        "error",
        None
    )

    try:

        with st.spinner(
            "正在连接 A股行情服务器..."
        ):

            result = test_market()

        st.success(
            "🟢 A股行情服务器连接成功"
        )

        st.write(
            "成功获取行情数量：",
            len(result)
        )

        rows = []

        for name, code in SECTORS:

            item = result.get(code)

            if item:

                rows.append({
                    "板块": name,
                    "ETF代码": code,
                    "当前价格": item["price"],
                    "涨跌幅": item["change"]
                })

        if rows:

            df = pd.DataFrame(
                rows
            )

            st.subheader(
                "📊 板块实时行情"
            )

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.warning(
                "服务器连接成功，但没有取得板块行情。"
            )

    except Exception as e:

        st.error(
            "🔴 A股行情连接失败"
        )

        st.code(
            traceback.format_exc(),
            language="text"
        )

        st.info(
            "请把上面的完整错误信息发给我。"
        )


# =========================
# 初始提示
# =========================

else:

    st.info(
        "点击上方「测试 A股实时行情」开始测试。"
    )

st.divider()

st.caption(
    "复利人生 V1.1｜当前阶段："
    "先验证云端服务器能否获取真实 A股行情"
)
