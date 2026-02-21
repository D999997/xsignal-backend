# ai/multi_tf.py
from __future__ import annotations

from ai.data_feed import fetch_ohlcv_binance
from ai.scoring import extract_features


def _trend_dir(df) -> int:
    """
    Simple direction from last close change:
    +1 bullish, -1 bearish
    """
    if len(df) < 2:
        return 0
    return 1 if df["close"].iloc[-1] >= df["close"].iloc[-2] else -1


def _structure_side(df) -> str:
    """
    Structure side based on breakout of prior 20 high/low (same logic family as your signal engine).
    Returns: "buy", "sell", or "none"
    """
    if len(df) < 25:
        return "none"

    last_close = df["close"].iloc[-1]
    prev_hh = df["high"].rolling(20).max().iloc[-2]
    prev_ll = df["low"].rolling(20).min().iloc[-2]

    if last_close > prev_hh:
        return "buy"
    if last_close < prev_ll:
        return "sell"
    return "none"


def multi_tf_confirm(symbol: str):
    """
    Fetch 3 TFs and confirm alignment.
    Returns:
      ok (bool), side ("buy"/"sell"), features bundle {"f5","f15","f1h"}
    This bundle is 100% compatible with calculate_xscore().
    """
    # ✅ Use keyword args so it matches your fetch_ohlcv_binance signature
    df_5m = fetch_ohlcv_binance(symbol=symbol, interval="5m", limit=300)
    df_15m = fetch_ohlcv_binance(symbol=symbol, interval="15m", limit=300)
    df_1h = fetch_ohlcv_binance(symbol=symbol, interval="1h", limit=300)

    # ✅ Features for xscore (keys: structure_strength, trend_strength, momentum, volatility)
    f5 = extract_features(df_5m)
    f15 = extract_features(df_15m)
    f1h = extract_features(df_1h)

    # ✅ Decide side from structure breakout on 5m
    side = _structure_side(df_5m)
    if side not in ("buy", "sell"):
        return False, "none", {"f5": f5, "f15": f15, "f1h": f1h}

    want_dir = 1 if side == "buy" else -1

    # ✅ Trend direction must align on 15m + 1h
    trend_ok = (_trend_dir(df_15m) == want_dir) and (_trend_dir(df_1h) == want_dir)

    # ✅ Basic strength filters (tune these)
    structure_ok = f5["structure_strength"] >= 0.25
    higher_tf_trend_ok = (f15["trend_strength"] >= 0.25) and (f1h["trend_strength"] >= 0.20)

    ok = trend_ok and structure_ok and higher_tf_trend_ok

    return ok, side, {"f5": f5, "f15": f15, "f1h": f1h}