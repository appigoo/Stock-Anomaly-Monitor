"""
股票異動監控系統 v2 — 上升浪預警版
新增訊號：
  ① 均線收斂偵測（能量壓縮預警）
  ② EMA 金叉偵測（EMA5 上穿 EMA10）
  ③ 均線多頭排列確認（EMA5>10>20 且斜率向上）
  ④ 成交量爆量（量比）
  ⑤ 股價偏離均線
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import datetime
from zoneinfo import ZoneInfo

# ── 頁面設定 ──────────────────────────────────────────────
st.set_page_config(
    page_title="股票異動監控 v2",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Noto+Sans+TC:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans TC', sans-serif;
    background-color: #FAF7F2;
    color: #2C2416;
}
.stApp { background-color: #FAF7F2; }
h1, h2, h3 { font-family: 'IBM Plex Mono', monospace; color: #3D2B1F; }

/* ── 報價卡 ── */
.metric-card {
    background: #FFFDF8;
    border: 1.5px solid #E8DFD0;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 8px;
    font-family: 'IBM Plex Mono', monospace;
    transition: border-color 0.3s;
}
.metric-card.has-signal { border-color: #FF8C00; border-width: 2px; }
.metric-card .ticker  { font-size: 1.1rem; font-weight: 600; color: #3D2B1F; }
.metric-card .price   { font-size: 1.3rem; font-weight: 600; }
.metric-card .label   { font-size: 0.68rem; color: #8C7B6B; margin-top: 4px; }
.metric-card .val     { font-size: 0.88rem; font-weight: 600; }

/* ── 訊號徽章 ── */
.badge {
    display: inline-block;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    padding: 2px 8px;
    border-radius: 3px;
    margin: 2px 3px 2px 0;
    font-weight: 600;
    letter-spacing: 0.05em;
}
.badge-convergence { background: #FFF3E0; color: #E65100; border: 1px solid #FFB74D; }
.badge-golden      { background: #E8F5E9; color: #1B5E20; border: 1px solid #66BB6A; }
.badge-bullish     { background: #E3F2FD; color: #0D47A1; border: 1px solid #64B5F6; }
.badge-vol         { background: #FFF8E1; color: #F57F17; border: 1px solid #FFD54F; }
.badge-deviation   { background: #FCE4EC; color: #880E4F; border: 1px solid #F48FB1; }
.badge-gap_up   { background: #E8F5E9; color: #1B5E20; border: 1px solid #66BB6A; }
.badge-gap_down { background: #FCE4EC; color: #880E4F; border: 1px solid #F48FB1; }
.badge-gap_combo{ background: #FFF3E0; color: #E65100; border: 1px solid #FFB74D; }
.badge-none     { background: #F5F5F5; color: #9E9E9E; border: 1px solid #E0E0E0; }

.alert-gap_up   { background: #E8F5E9; border-left: 4px solid #2E7D32; color: #1B5E20; }
.alert-gap_down { background: #FCE4EC; border-left: 4px solid #C62828; color: #7A0030; }

/* ── 警報卡 ── */
.alert-card {
    border-radius: 8px;
    padding: 10px 16px;
    margin: 4px 0;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    line-height: 1.5;
}
.alert-convergence { background: #FFF3E0; border-left: 4px solid #FF6D00; color: #7A3B00; }
.alert-golden      { background: #E8F5E9; border-left: 4px solid #2E7D32; color: #1B5E20; }
.alert-bullish     { background: #E3F2FD; border-left: 4px solid #1565C0; color: #0D47A1; }
.alert-vol         { background: #FFF8E1; border-left: 4px solid #F9A825; color: #6D4C00; }
.alert-price_up    { background: #E8F5E9; border-left: 4px solid #43A047; color: #1B5E20; }
.alert-price_down  { background: #FCE4EC; border-left: 4px solid #E91E63; color: #7A0030; }

/* ── 狀態點 ── */
.status-dot {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; margin-right: 6px;
    animation: pulse 1.4s infinite;
}
.dot-green { background: #43A047; }
.dot-grey  { background: #9E9E9E; animation: none; }
@keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.3;} }

.sidebar-section {
    background: #FFFDF8; border: 1px solid #E8DFD0;
    border-radius: 8px; padding: 12px; margin-bottom: 12px;
}
div[data-testid="stSidebar"] { background-color: #F5F0E8; }

/* ── 市場狀態 ── */
.market-open   { color: #27AE60; font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; }
.market-closed { color: #E74C3C; font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)


# ── 預設 Watchlist ────────────────────────────────────────
DEFAULT_WATCHLIST = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]

# ── Session State 初始化 ──────────────────────────────────
def init_state():
    defaults = {
        "watchlist":         DEFAULT_WATCHLIST.copy(),
        "monitoring":        False,
        "alert_log":         [],
        "last_data":         {},
        "tg_token":          "",
        "tg_chat_id":        "",
        # 成交量設定
        "vol_mult":          3.0,
        "vol_period":        20,
        # 偏離均線設定
        "price_dev_pct":     3.0,
        "ma_period":         20,
        # EMA 收斂設定
        "convergence_pct":   5.0,   # EMA5/10/20 最大差距 ÷ 現價 < X% 視為收斂
        # 輪詢
        "check_interval":    60,
        "tg_mute":           False,
        "sent_alerts":       set(),
        # EMA 狀態記錄：用於金叉「首次確認」去重（ticker → bool: 上次 EMA5 是否 > EMA10）
        "prev_ema_above":    {},    # {ticker: True/False}
        # 訊號開關
        "sig_convergence":   True,
        "sig_golden":        True,
        "sig_bullish":       True,
        "sig_vol":           True,
        "sig_deviation":     True,
        "sig_gap":           True,
        # 跳空設定
        "gap_min_pct":       1.0,    # 跳空缺口最小幅度 %
        "gap_vol_mult":      2.0,    # 跳空+爆量組合，量比閾值
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ── 市場開閉市判斷 ────────────────────────────────────────
def is_market_open() -> bool:
    """判斷美股是否在正常交易時段（ET 09:30–16:00，週一至週五）"""
    now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:  # 週六日
        return False
    market_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= now_et <= market_close

def market_status_html() -> str:
    if is_market_open():
        return '<span class="market-open">● 美股交易中</span>'
    now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    return f'<span class="market-closed">● 美股休市 ({now_et.strftime("%a %H:%M ET")})</span>'


# ── Telegram ─────────────────────────────────────────────
def send_telegram(token: str, chat_id: str, msg: str) -> bool:
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=8)
        return r.status_code == 200
    except Exception:
        return False


# ── EMA 計算（純 Python ewm，無 TA-Lib）─────────────────
def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


# ── 資料抓取與指標計算 ────────────────────────────────────
@st.cache_data(ttl=58)
def fetch_stock(ticker: str, vol_period: int, ma_period: int, conv_pct: float, gap_vol_mult: float = 2.0):
    try:
        lookback = max(vol_period, ma_period, 200) + 10
        df = yf.download(ticker, period=f"{lookback}d", interval="1d",
                         progress=False, auto_adjust=True)
        if df.empty or len(df) < 30:
            return None

        # 攤平 MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close  = df["Close"]
        volume = df["Volume"]

        # ── 基本價格數據 ──
        price_now  = float(close.iloc[-1])
        price_prev = float(close.iloc[-2])
        change_pct = (price_now - price_prev) / price_prev * 100

        # ── 成交量（用前一日收盤計算均量，排除今日）──
        avg_vol   = float(volume.iloc[-(vol_period+1):-1].mean())
        vol_today = int(volume.iloc[-1])
        vol_ratio = vol_today / avg_vol if avg_vol > 0 else 0

        # ── MA 偏離（用前N日均價對比今日現價）──
        ma_val    = float(close.iloc[-(ma_period+1):-1].mean())   # 昨日為基準
        dev_pct   = (price_now - ma_val) / ma_val * 100

        # ── EMA 計算 ──
        ema5   = calc_ema(close, 5)
        ema10  = calc_ema(close, 10)
        ema20  = calc_ema(close, 20)

        e5_now,  e5_prev  = float(ema5.iloc[-1]),  float(ema5.iloc[-2])
        e10_now, e10_prev = float(ema10.iloc[-1]), float(ema10.iloc[-2])
        e20_now           = float(ema20.iloc[-1])

        # ── ① 均線收斂偵測 ──
        # 三條 EMA 的最大差距 ÷ 現價
        ema_spread_pct = (max(e5_now, e10_now, e20_now) - min(e5_now, e10_now, e20_now)) / price_now * 100
        is_converging  = ema_spread_pct < conv_pct

        # ── ② EMA5 金叉 EMA10（跨 K 棒判斷，由主迴圈覆寫）──
        # 此處保留 intra-bar 初始值；主迴圈會用 prev_ema_above 做跨輪詢判斷
        golden_cross = (e5_prev <= e10_prev) and (e5_now > e10_now)

        # ── ③ 多頭排列 ──
        # EMA5 > EMA10 > EMA20，且 EMA5、EMA10 斜率皆為正
        bullish_align = (
            e5_now > e10_now > e20_now
            and e5_now > float(ema5.iloc[-2])     # EMA5 斜率向上
            and e10_now > float(ema10.iloc[-2])   # EMA10 斜率向上
        )

        # ── EMA 斜率百分比（顯示用）──
        e5_slope  = (e5_now - e5_prev) / e5_prev * 100
        e10_slope = (e10_now - e10_prev) / e10_prev * 100

        # ── ④ 跳空缺口偵測 ──
        open_today = float(df["Open"].iloc[-1])
        high_prev  = float(df["High"].iloc[-2])
        low_prev   = float(df["Low"].iloc[-2])

        gap_up   = open_today > high_prev   # 向上跳空：今開 > 昨高
        gap_down = open_today < low_prev    # 向下跳空：今開 < 昨低

        if gap_up:
            gap_pct = (open_today - high_prev) / high_prev * 100
        elif gap_down:
            gap_pct = (open_today - low_prev) / low_prev * 100   # 負值
        else:
            gap_pct = 0.0

        # 跳空 + 爆量組合（最強形態）— 使用用戶設定的量比閾值
        gap_with_vol = (gap_up or gap_down) and (vol_ratio >= gap_vol_mult)

        return {
            "ticker":         ticker,
            "price":          price_now,
            "price_prev":     price_prev,
            "change_pct":     change_pct,
            "vol_today":      vol_today,
            "avg_vol":        int(avg_vol),
            "vol_ratio":      vol_ratio,
            "ma_val":         ma_val,
            "dev_pct":        dev_pct,
            "ema5":           e5_now,
            "ema10":          e10_now,
            "ema20":          e20_now,
            "ema_spread_pct": ema_spread_pct,
            "is_converging":  is_converging,
            "golden_cross":   golden_cross,
            "bullish_align":  bullish_align,
            "e5_slope":       e5_slope,
            "e10_slope":      e10_slope,
            "open_today":     open_today,
            "gap_up":         gap_up,
            "gap_down":       gap_down,
            "gap_pct":        gap_pct,
            "gap_with_vol":   gap_with_vol,
            "ts": datetime.datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M:%S ET"),
        }
    except Exception:
        return None


# ── 異動偵測 ─────────────────────────────────────────────
def check_alerts(d: dict) -> list[dict]:
    alerts = []
    ticker = d["ticker"]
    ts     = d["ts"]

    # ① 均線收斂
    if st.session_state.sig_convergence and d["is_converging"]:
        alerts.append({
            "type":  "convergence",
            "ticker": ticker,
            "msg": (f"🔵 [{ticker}] 均線收斂預警！\n"
                    f"EMA5/10/20 最大差距僅 {d['ema_spread_pct']:.2f}%（閾值 {st.session_state.convergence_pct}%）\n"
                    f"EMA5:{d['ema5']:.3f} / EMA10:{d['ema10']:.3f} / EMA20:{d['ema20']:.3f}\n"
                    f"⚠️ 能量壓縮中，注意方向性突破"),
            "time": ts,
        })

    # ② 金叉
    if st.session_state.sig_golden and d["golden_cross"]:
        alerts.append({
            "type":  "golden",
            "ticker": ticker,
            "msg": (f"🟢 [{ticker}] EMA5 金叉 EMA10！\n"
                    f"EMA5:{d['ema5']:.3f} 上穿 EMA10:{d['ema10']:.3f}\n"
                    f"斜率 EMA5:{d['e5_slope']:+.3f}% / EMA10:{d['e10_slope']:+.3f}%\n"
                    f"📈 短期趨勢轉強訊號"),
            "time": ts,
        })

    # ③ 多頭排列
    if st.session_state.sig_bullish and d["bullish_align"]:
        alerts.append({
            "type":  "bullish",
            "ticker": ticker,
            "msg": (f"🔷 [{ticker}] 均線多頭排列確認！\n"
                    f"EMA5 > EMA10 > EMA20，且斜率皆向上\n"
                    f"EMA5:{d['ema5']:.3f} / EMA10:{d['ema10']:.3f} / EMA20:{d['ema20']:.3f}\n"
                    f"🚀 上升浪結構成立"),
            "time": ts,
        })

    # ④ 爆量
    if st.session_state.sig_vol and d["vol_ratio"] >= st.session_state.vol_mult:
        alerts.append({
            "type":  "vol",
            "ticker": ticker,
            "msg": (f"📊 [{ticker}] 成交量爆量！量比 {d['vol_ratio']:.1f}x\n"
                    f"均量 {d['avg_vol']:,} → 今日 {d['vol_today']:,}"),
            "time": ts,
        })

    # ⑤ 跳空缺口 + 爆量組合
    if st.session_state.sig_gap:
        min_gap = st.session_state.gap_min_pct
        if d["gap_up"] and abs(d["gap_pct"]) >= min_gap:
            combo = d["gap_with_vol"]
            strength = "🚀 跳空+爆量強力訊號！" if combo else "📈 向上跳空缺口"
            alerts.append({
                "type":   "gap_up",
                "ticker": ticker,
                "msg": (f"⬆️ [{ticker}] 向上跳空 +{d['gap_pct']:.2f}%\n"
                        f"今開 ${d['open_today']:.2f} 高於昨高，量比 {d['vol_ratio']:.1f}x\n"
                        f"{strength}"),
                "time": ts,
            })
        elif d["gap_down"] and abs(d["gap_pct"]) >= min_gap:
            combo = d["gap_with_vol"]
            strength = "💥 跳空+爆量崩跌訊號！" if combo else "📉 向下跳空缺口"
            alerts.append({
                "type":   "gap_down",
                "ticker": ticker,
                "msg": (f"⬇️ [{ticker}] 向下跳空 {d['gap_pct']:.2f}%\n"
                        f"今開 ${d['open_today']:.2f} 低於昨低，量比 {d['vol_ratio']:.1f}x\n"
                        f"{strength}"),
                "time": ts,
            })

    # ⑥ 偏離均線    if st.session_state.sig_deviation:
        if d["dev_pct"] >= st.session_state.price_dev_pct:
            alerts.append({
                "type":  "price_up",
                "ticker": ticker,
                "msg": (f"🔺 [{ticker}] 偏離MA{st.session_state.ma_period} +{d['dev_pct']:.1f}%\n"
                        f"現價 ${d['price']:.2f} / MA ${d['ma_val']:.2f}"),
                "time": ts,
            })
        elif d["dev_pct"] <= -st.session_state.price_dev_pct:
            alerts.append({
                "type":  "price_down",
                "ticker": ticker,
                "msg": (f"🔻 [{ticker}] 偏離MA{st.session_state.ma_period} {d['dev_pct']:.1f}%\n"
                        f"現價 ${d['price']:.2f} / MA ${d['ma_val']:.2f}"),
                "time": ts,
            })

    return alerts


# ── Sidebar ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📡 監控設定")

    # Watchlist
    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown("**📋 監控清單**")
    wl_input = st.text_area("每行一個 Ticker", "\n".join(st.session_state.watchlist),
                             height=150, label_visibility="collapsed")
    raw_tickers = [t.strip().upper() for t in wl_input.split("\n") if t.strip()]

    # 驗證 Ticker 格式（基本檢查）
    valid, invalid = [], []
    for t in raw_tickers:
        if t.isalpha() and 1 <= len(t) <= 5:
            valid.append(t)
        else:
            invalid.append(t)
    if invalid:
        st.warning(f"⚠️ 無效 Ticker：{', '.join(invalid)}")
    st.session_state.watchlist = valid
    st.markdown('</div>', unsafe_allow_html=True)

    # 訊號開關
    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown("**🔔 訊號開關**")
    st.session_state.sig_convergence = st.checkbox("🔵 均線收斂預警",   st.session_state.sig_convergence)
    st.session_state.sig_golden      = st.checkbox("🟢 EMA5 金叉 EMA10", st.session_state.sig_golden)
    st.session_state.sig_bullish     = st.checkbox("🔷 多頭排列確認",    st.session_state.sig_bullish)
    st.session_state.sig_vol         = st.checkbox("📊 成交量爆量",      st.session_state.sig_vol)
    st.session_state.sig_deviation   = st.checkbox("📏 偏離均線",        st.session_state.sig_deviation)
    st.session_state.sig_gap        = st.checkbox("⬆️ 跳空缺口",         st.session_state.sig_gap)
    st.markdown('</div>', unsafe_allow_html=True)

    # 跳空設定
    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown("**⬆️ 跳空缺口設定**")
    st.session_state.gap_min_pct  = st.slider("最小跳空幅度 (%)", 0.5, 5.0, st.session_state.gap_min_pct, 0.5)
    st.session_state.gap_vol_mult = st.slider("跳空+爆量量比閾值", 1.5, 5.0, st.session_state.gap_vol_mult, 0.5)
    st.caption("跳空 + 量比 ≥ 此值 = 組合強力訊號")

    # EMA 收斂設定
    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown("**🔵 均線收斂閾值**")
    st.session_state.convergence_pct = st.slider(
        "EMA5/10/20 最大差距 ÷ 股價 < X%", 1.0, 15.0, st.session_state.convergence_pct, 0.5)
    st.caption("數值越小 = 越嚴格，建議 3–6%")
    st.markdown('</div>', unsafe_allow_html=True)

    # 成交量設定
    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown("**📊 成交量異動**")
    st.session_state.vol_mult   = st.slider("量比觸發閾值 (x倍)", 1.5, 10.0, st.session_state.vol_mult, 0.5)
    st.session_state.vol_period = st.slider("平均量計算天數",      5,   60,  st.session_state.vol_period, 5)
    st.markdown('</div>', unsafe_allow_html=True)

    # 偏離均線設定
    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown("**📏 偏離均線**")
    st.session_state.price_dev_pct = st.slider("偏離觸發 (%)", 1.0, 20.0, st.session_state.price_dev_pct, 0.5)
    st.session_state.ma_period     = st.selectbox("均線天數 (MA)", [5, 10, 20, 50, 200], index=2)
    st.markdown('</div>', unsafe_allow_html=True)

    # 輪詢設定
    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown("**⏱ 輪詢間隔**")
    st.session_state.check_interval = st.slider("秒數", 30, 300, st.session_state.check_interval, 30)
    st.markdown('</div>', unsafe_allow_html=True)

    # Telegram
    st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
    st.markdown("**✈️ Telegram 通知**")
    st.session_state.tg_token   = st.text_input("Bot Token",  st.session_state.tg_token,   type="password")
    st.session_state.tg_chat_id = st.text_input("Chat ID",    st.session_state.tg_chat_id)
    st.session_state.tg_mute    = st.checkbox("🔇 暫停推送",  st.session_state.tg_mute)
    if st.button("📤 測試 Telegram"):
        ok = send_telegram(st.session_state.tg_token, st.session_state.tg_chat_id,
                           "✅ 異動監控系統連線正常！\n5個訊號模組已就緒。")
        st.success("發送成功 ✓") if ok else st.error("失敗，請檢查 Token / Chat ID")
    st.markdown('</div>', unsafe_allow_html=True)

    # 啟動/停止
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ 啟動", use_container_width=True, type="primary"):
            st.session_state.monitoring    = True
            st.session_state.sent_alerts   = set()
            st.session_state.prev_ema_above = {}   # ← 重置金叉狀態，避免舊記憶誤判
    with c2:
        if st.button("⏹ 停止", use_container_width=True):
            st.session_state.monitoring = False


# ── 主畫面 ───────────────────────────────────────────────
st.markdown("# 📡 股票異動監控 v2 — 上升浪預警")

# 狀態列
dot    = "dot-green" if st.session_state.monitoring else "dot-grey"
status = "監控中" if st.session_state.monitoring else "已停止"
st.markdown(
    f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.82rem;margin-bottom:4px;">'
    f'<span class="status-dot {dot}"></span>{status} &nbsp;｜&nbsp; {market_status_html()}'
    f'</div>',
    unsafe_allow_html=True
)
st.markdown("---")

# 訊號說明
with st.expander("📖 訊號說明 — 如何捕捉上升浪", expanded=False):
    st.markdown("""
    | 訊號 | 觸發條件 | 意義 |
    |------|----------|------|
    | 🔵 **均線收斂** | EMA5/10/20 最大差距 ÷ 股價 < 設定% | 能量壓縮中，突破方向待確認，**最早期預警** |
    | 🟢 **EMA5 金叉** | EMA5 由下往上穿越 EMA10 | 短期趨勢轉強，上升浪起步確認 |
    | 🔷 **多頭排列** | EMA5 > EMA10 > EMA20 且斜率向上 | 上升浪結構成立，趨勢最強確認 |
    | ⬆️ **向上跳空** | 今日開盤 > 昨日最高，缺口 ≥ 設定% | 方向性突破，無賣壓承接 |
    | 🚀 **跳空+爆量** | 跳空缺口 + 量比 ≥ 閾值 | **你圖中的爆升形態**，機構追倉訊號 |
    | 📊 **成交量爆量** | 今日量 ÷ N日均量 > 設定倍數 | 主力進場，配合金叉效力倍增 |
    | 📏 **偏離均線** | 股價偏離 MA > 設定% | 超買/超賣提示 |

    **最佳入市組合（按你截圖的邏輯）：均線收斂 → 跳空+爆量 → EMA金叉 → 多頭排列確認**
    """)

# 雙欄佈局
col_main, col_alerts = st.columns([3, 2], gap="medium")
with col_main:
    st.markdown("### 即時報價 & 訊號")
    price_ph = st.empty()
with col_alerts:
    st.markdown("### 異動警報")
    alert_ph = st.empty()


# ── 渲染報價卡 ────────────────────────────────────────────
def badge(label: str, cls: str) -> str:
    return f'<span class="badge {cls}">{label}</span>'

def render_price_cards(last_data: dict) -> str:
    if not last_data:
        return '<p style="color:#8C7B6B;font-size:0.85rem;">等待資料載入...</p>'
    cards = []
    for ticker, d in last_data.items():
        chg   = d["change_pct"]
        chg_c = "#27AE60" if chg >= 0 else "#E74C3C"
        chg_s = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"

        # 訊號徽章
        badges = ""
        has_signal = False
        if d["is_converging"]:
            badges += badge("🔵 收斂", "badge-convergence"); has_signal = True
        if d["golden_cross"]:
            badges += badge("🟢 金叉", "badge-golden"); has_signal = True
        if d["bullish_align"]:
            badges += badge("🔷 多頭", "badge-bullish"); has_signal = True
        if d["vol_ratio"] >= st.session_state.vol_mult:
            badges += badge(f"📊 {d['vol_ratio']:.1f}x", "badge-vol"); has_signal = True
        if abs(d["dev_pct"]) >= st.session_state.price_dev_pct:
            badges += badge(f"📏 {d['dev_pct']:+.1f}%", "badge-deviation"); has_signal = True
        if d.get("gap_up") and abs(d.get("gap_pct", 0)) >= st.session_state.gap_min_pct:
            cls = "badge-gap_combo" if d.get("gap_with_vol") else "badge-gap_up"
            badges += badge(f"⬆️ 跳空+{d['gap_pct']:.1f}%", cls); has_signal = True
        if d.get("gap_down") and abs(d.get("gap_pct", 0)) >= st.session_state.gap_min_pct:
            cls = "badge-gap_combo" if d.get("gap_with_vol") else "badge-gap_down"
            badges += badge(f"⬇️ 跳空{d['gap_pct']:.1f}%", cls); has_signal = True
        if not badges:
            badges = badge("無異動", "badge-none")

        card_cls = "metric-card has-signal" if has_signal else "metric-card"
        cards.append(f"""
        <div class="{card_cls}">
          <div style="display:flex;justify-content:space-between;align-items:baseline;">
            <span class="ticker">{ticker}</span>
            <span class="price" style="color:{chg_c}">${d['price']:.2f}
              <span style="font-size:0.8rem;">{chg_s}</span></span>
          </div>
          <div style="margin:6px 0 4px;">{badges}</div>
          <div style="display:flex;gap:20px;margin-top:6px;flex-wrap:wrap;">
            <div>
              <div class="label">EMA5 / 10 / 20</div>
              <div class="val" style="font-size:0.78rem;">
                {d['ema5']:.2f} / {d['ema10']:.2f} / {d['ema20']:.2f}
              </div>
            </div>
            <div>
              <div class="label">EMA 差距</div>
              <div class="val" style="color:{'#E65100' if d['is_converging'] else '#2C2416'};">
                {d['ema_spread_pct']:.2f}%
              </div>
            </div>
            <div>
              <div class="label">量比</div>
              <div class="val" style="color:{'#FF8C00' if d['vol_ratio']>=st.session_state.vol_mult else '#2C2416'};">
                {d['vol_ratio']:.1f}x
              </div>
            </div>
          </div>
          <div style="font-size:0.65rem;color:#B0A090;margin-top:5px;font-family:'IBM Plex Mono',monospace;">
            {d['ts']}
          </div>
        </div>
        """)
    return "".join(cards)


# ── 渲染警報欄 ────────────────────────────────────────────
def render_alerts(log: list) -> str:
    if not log:
        return '<p style="color:#8C7B6B;font-size:0.85rem;">尚無異動警報</p>'
    items = []
    for a in reversed(log[-40:]):
        cls = f"alert-{a['type']}"
        msg_html = a["msg"].replace("\n", "<br>")
        items.append(f'<div class="alert-card {cls}"><b>[{a["time"]}]</b><br>{msg_html}</div>')
    return "".join(items)


# ── 主輪詢 ────────────────────────────────────────────────
if st.session_state.monitoring:
    # 閉市期間提示但不停止（日線數據仍可更新）
    new_data = {}
    for ticker in st.session_state.watchlist:
        d = fetch_stock(
            ticker,
            st.session_state.vol_period,
            st.session_state.ma_period,
            st.session_state.convergence_pct,
            st.session_state.gap_vol_mult,      # ← 修正：傳入用戶設定值
        )
        if d:
            new_data[ticker] = d
        # 若 fetch 失敗給出提示
        elif ticker in st.session_state.last_data:
            new_data[ticker] = st.session_state.last_data[ticker]  # 保留上次資料

    st.session_state.last_data = new_data

    # ── 跨輪詢金叉判斷（首次確認邏輯）────────────────────────
    # 比較「上次輪詢時 EMA5 是否 > EMA10」與「本次」的狀態變化
    # 只有從「否→是」的那一次才算金叉，避免多頭排列期間每輪詢都觸發
    for ticker, d in new_data.items():
        ema5_above_now = d["ema5"] > d["ema10"]
        ema5_above_prev = st.session_state.prev_ema_above.get(ticker, ema5_above_now)
        # 覆寫 fetch_stock 內的 golden_cross：只有「上次在下，這次在上」才算
        d["golden_cross"] = (not ema5_above_prev) and ema5_above_now
        # 更新狀態記錄
        st.session_state.prev_ema_above[ticker] = ema5_above_now

    # 偵測警報（盤中才推 Telegram，避免閉市假訊號）
    today_str = datetime.datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")
    for ticker, d in new_data.items():
        for alert in check_alerts(d):
            # 跳空缺口是全天性質 → 用日期去重，防止整天洗版
            # 其他訊號 → 用 HH:MM 去重（同分鐘只發一次）
            if alert["type"] in ("gap_up", "gap_down"):
                key = f"{ticker}_{alert['type']}_{today_str}"
            else:
                key = f"{ticker}_{alert['type']}_{alert['time'][:5]}"
            if key not in st.session_state.sent_alerts:
                st.session_state.sent_alerts.add(key)
                st.session_state.alert_log.append(alert)
                # 收斂訊號在閉市也推（提前佈局用），其他盤中才推
                if not st.session_state.tg_mute:
                    if alert["type"] == "convergence" or is_market_open():
                        send_telegram(
                            st.session_state.tg_token,
                            st.session_state.tg_chat_id,
                            alert["msg"]
                        )

# 渲染
price_ph.markdown(render_price_cards(st.session_state.last_data), unsafe_allow_html=True)
alert_ph.markdown(render_alerts(st.session_state.alert_log), unsafe_allow_html=True)

# ── 警報記錄 ─────────────────────────────────────────────
if st.session_state.alert_log:
    st.markdown("---")
    with st.expander("📋 完整警報記錄"):
        df_log = pd.DataFrame(st.session_state.alert_log)[["time", "ticker", "type", "msg"]]
        df_log.columns = ["時間", "股票", "類型", "訊息"]
        st.dataframe(df_log, use_container_width=True, hide_index=True)
        csv = df_log.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇ 下載 CSV", csv, "alert_log.csv", "text/csv")

    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("🗑 清除記錄"):
            st.session_state.alert_log   = []
            st.session_state.sent_alerts = set()
            st.rerun()

# ── 自動刷新 ─────────────────────────────────────────────
if st.session_state.monitoring:
    time.sleep(st.session_state.check_interval)
    st.rerun()
