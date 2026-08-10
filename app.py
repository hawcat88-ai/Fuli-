
import time
from datetime import datetime
import requests
import pandas as pd
import numpy as np
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="复利人生 V1.0｜A股自动扫描",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

SECTORS = [
    {"name":"半导体","code":"512480"},
    {"name":"人工智能","code":"159819"},
    {"name":"军工","code":"512660"},
    {"name":"电力","code":"159611"},
    {"name":"有色金属","code":"512400"},
]

EAST_FIELDS = "f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18,f124"
TIMEOUT = 8

def east_secid(code):
    code = str(code)
    return ("1." if code.startswith(("6","5")) else "0.") + code

def east_url_quotes(codes):
    secids = ",".join(east_secid(c) for c in codes)
    return (
        "https://push2.eastmoney.com/api/qt/ulist.np/get"
        f"?fltt=2&invt=2&fields={EAST_FIELDS}&secids={secids}"
    )

def east_url_kline(code, count=120):
    return (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        "?fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        "&klt=101&fqt=1&beg=0&end=20500101"
        f"&lmt={count}&secid={east_secid(code)}"
    )

def fetch_east_quotes(codes):
    r = requests.get(east_url_quotes(codes), timeout=TIMEOUT,
                     headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    obj = r.json()
    diff = (obj.get("data") or {}).get("diff")
    if not diff:
        raise RuntimeError("东方财富实时行情返回为空")
    rows = diff if isinstance(diff, list) else list(diff.values())
    out = {}
    for d in rows:
        code = str(d.get("f12") or "")
        if not code:
            continue
        out[code] = {
            "name": d.get("f14") or "",
            "code": code,
            "price": float(d.get("f2") or 0),
            "pct": float(d.get("f3") or 0),
            "change": float(d.get("f4") or 0),
            "volume": float(d.get("f5") or 0),
            "amount": float(d.get("f6") or 0),
            "high": float(d.get("f15") or 0),
            "low": float(d.get("f16") or 0),
            "open": float(d.get("f17") or 0),
            "prev": float(d.get("f18") or 0),
            "time": d.get("f124") or "",
        }
    if not out:
        raise RuntimeError("东方财富实时行情解析为空")
    return out

def fetch_east_kline(code, count=120):
    r = requests.get(east_url_kline(code, count), timeout=TIMEOUT,
                     headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    obj = r.json()
    rows = (obj.get("data") or {}).get("klines")
    if not isinstance(rows, list) or len(rows) < 60:
        raise RuntimeError(f"{code} K线不足60根")
    parsed = []
    for row in rows:
        x = str(row).split(",")
        if len(x) < 6:
            continue
        try:
            parsed.append({
                "date": x[0],
                "open": float(x[1]),
                "close": float(x[2]),
                "high": float(x[3]),
                "low": float(x[4]),
                "volume": float(x[5]),
            })
        except Exception:
            pass
    if len(parsed) < 60:
        raise RuntimeError(f"{code} K线解析不足60根")
    return pd.DataFrame(parsed)

def sma(s, n):
    return float(s.tail(n).mean())

def rsi(closes, n=14):
    d = closes.diff().dropna().tail(n)
    gain = d.clip(lower=0).sum()
    loss = (-d.clip(upper=0)).sum()
    if loss == 0:
        return 100.0
    return float(100 - 100 / (1 + gain / loss))

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def macd(closes):
    dif = ema(closes, 12) - ema(closes, 26)
    dea = ema(dif, 9)
    return float(dif.iloc[-1]), float(dea.iloc[-1]), float((dif-dea).iloc[-1])

def build_row(sec, quote, kline, market_pct):
    c = kline["close"]
    v = kline["volume"]
    price = quote["price"] or float(c.iloc[-1])
    high60 = float(kline["high"].tail(60).max())
    low60 = float(kline["low"].tail(60).min())
    ma5, ma10, ma20, ma60 = [sma(c, n) for n in (5,10,20,60)]
    rrsi = rsi(c, 14)
    dif, dea, hist = macd(c)
    avg60 = sma(v, 60)
    vol_ratio = quote["volume"] / avg60 * 100 if avg60 else 0
    drawdown = (high60-price)/high60*100 if high60 else 0
    rel = quote["pct"] - market_pct

    if price > ma20 and hist > 0:
        dragon = "已企稳"
        dragon_score = 85
    elif price > ma10 or rrsi > 50:
        dragon = "企稳中"
        dragon_score = 65
    elif price < ma20 and rrsi < 40:
        dragon = "继续下跌"
        dragon_score = 15
    else:
        dragon = "未企稳"
        dragon_score = 35

    # V1 测试评分：只使用真实可计算的行情因子，不虚构估值/政策数据
    score = 0
    score += max(0, min(25, (35-drawdown) * 0.8))
    score += max(0, min(20, (vol_ratio-50) * 0.4))
    score += max(0, min(20, (rrsi-30) * 0.6))
    score += max(0, min(20, rel * 2))
    score += dragon_score * 0.15
    score = max(0, min(100, score))

    return {
        "板块": sec["name"],
        "ETF": sec["code"],
        "现价": price,
        "涨跌幅%": quote["pct"],
        "成交额": quote["amount"],
        "60日回撤%": drawdown,
        "量能比%": vol_ratio,
        "RSI14": rrsi,
        "MA20": ma20,
        "MA60": ma60,
        "MACD柱": hist,
        "相对大盘%": rel,
        "龙头状态": dragon,
        "机会评分": score,
        "数据时间": quote["time"],
        "_raw_quote": quote,
    }

@st.cache_data(ttl=20, show_spinner=False)
def scan_market():
    codes = [x["code"] for x in SECTORS] + ["000001"]
    quotes = fetch_east_quotes(codes)
    index = quotes.get("000001")
    if not index:
        raise RuntimeError("无法取得上证指数实时数据")
    market_pct = index["pct"]
    rows, errors = [], []
    for sec in SECTORS:
        try:
            q = quotes.get(sec["code"])
            if not q:
                raise RuntimeError("实时行情缺失")
            k = fetch_east_kline(sec["code"], 120)
            rows.append(build_row(sec, q, k, market_pct))
        except Exception as e:
            errors.append(f'{sec["name"]}: {e}')
    if not rows:
        raise RuntimeError("5个测试板块均未取得有效行情")
    return pd.DataFrame(rows), errors, index

st.title("📈 复利人生 V1.0")
st.caption("真实 A 股行情自动扫描测试版｜手机 / 平板可直接访问")

with st.sidebar:
    st.subheader("扫描控制")
    auto = st.toggle("每60秒自动刷新", value=True)
    if auto:
        st_autorefresh(interval=60_000, key="market_refresh")
    if st.button("🔄 立即扫描", use_container_width=True):
        scan_market.clear()
        st.rerun()

    st.divider()
    st.markdown("**本阶段只测试 5 个板块**")
    for s in SECTORS:
        st.write(f"• {s['name']}  `{s['code']}`")

try:
    df, errors, index = scan_market()
    st.success(f"🟢 实时行情连接成功 · 东方财富 · 上证 {index['pct']:+.2f}%")
    st.caption(f"最近扫描：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · 当前仅使用真实行情计算，不使用演示数据")

    cols = st.columns(4)
    cols[0].metric("扫描板块", len(df))
    cols[1].metric("最高机会评分", f"{df['机会评分'].max():.1f}")
    best = df.sort_values("机会评分", ascending=False).iloc[0]
    cols[2].metric("当前第一", best["板块"])
    cols[3].metric("第一涨跌", f"{best['涨跌幅%']:+.2f}%")

    st.subheader("🔥 自动扫描结果")
    show = df.sort_values("机会评分", ascending=False).copy()
    st.dataframe(
        show[["板块","ETF","现价","涨跌幅%","60日回撤%","量能比%","RSI14",
              "相对大盘%","龙头状态","机会评分","数据时间"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "现价": st.column_config.NumberColumn(format="%.3f"),
            "涨跌幅%": st.column_config.NumberColumn(format="%+.2f"),
            "60日回撤%": st.column_config.NumberColumn(format="%.2f"),
            "量能比%": st.column_config.NumberColumn(format="%.1f"),
            "RSI14": st.column_config.NumberColumn(format="%.1f"),
            "相对大盘%": st.column_config.NumberColumn(format="%+.2f"),
            "机会评分": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
        },
    )

    st.subheader("🎯 当前候选")
    top = show.iloc[0]
    st.info(
        f"**{top['板块']}**｜涨跌 {top['涨跌幅%']:+.2f}%｜"
        f"60日回撤 {top['60日回撤%']:.1f}%｜RSI {top['RSI14']:.1f}｜"
        f"量能比 {top['量能比%']:.1f}%｜相对大盘 {top['相对大盘%']:+.2f}%｜"
        f"评分 {top['机会评分']:.1f}"
    )

    if errors:
        with st.expander(f"⚠️ 部分板块数据异常（{len(errors)}）"):
            for e in errors:
                st.write("• " + e)

except Exception as e:
    st.error("🔴 A股行情连接失败")
    st.warning(str(e))
    st.info(
        "本测试版不会用随机数冒充行情。若数据源不可用，会明确显示失败原因。"
        "这一步用于验证云端数据层，确认后再扩展到20+板块和完整评分系统。"
    )
