import numpy as np
import pandas as pd
import ta

def compute_features(df: pd.DataFrame) -> dict:
    """
    Returns normalized features (0..1) so scoring is stable.
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # --- Trend: EMA slope alignment ---
    ema_fast = ta.trend.ema_indicator(close, window=20)
    ema_slow = ta.trend.ema_indicator(close, window=50)

    trend_dir = 1 if ema_fast.iloc[-1] > ema_slow.iloc[-1] else -1
    ema_slope = (ema_fast.iloc[-1] - ema_fast.iloc[-6]) / max(1e-9, abs(ema_fast.iloc[-6]))

    # Normalize slope: clamp into 0..1
    trend_strength = float(np.clip((abs(ema_slope) * 200), 0, 1))

    # --- Momentum: RSI proximity to extremes ---
    rsi = ta.momentum.rsi(close, window=14)
    r = float(rsi.iloc[-1])
    # Strong momentum when RSI far from 50
    momentum = float(np.clip(abs(r - 50) / 50, 0, 1))

    # --- Volatility: ATR relative to price ---
    atr = ta.volatility.average_true_range(high, low, close, window=14)
    atr_rel = float(atr.iloc[-1] / max(1e-9, close.iloc[-1]))
    volatility = float(np.clip(atr_rel * 80, 0, 1))  # scaled

    # --- Structure: breakout / range compression ---
    # structure_strength = how far price is outside last 20-bar range
    hh20 = high.rolling(20).max().iloc[-2]
    ll20 = low.rolling(20).min().iloc[-2]
    last_close = float(close.iloc[-1])

    if last_close > hh20:
        structure_strength = float(np.clip((last_close - hh20) / max(1e-9, atr.iloc[-1]), 0, 1))
        structure_side = "buy"
    elif last_close < ll20:
        structure_strength = float(np.clip((ll20 - last_close) / max(1e-9, atr.iloc[-1]), 0, 1))
        structure_side = "sell"
    else:
        structure_strength = 0.0
        structure_side = "none"

    return {
        "trend_dir": trend_dir,
        "trend_strength": trend_strength,
        "momentum": momentum,
        "volatility": volatility,
        "structure_strength": structure_strength,
        "structure_side": structure_side,
    }