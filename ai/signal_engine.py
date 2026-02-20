# ai/signal_engine.py
import pandas as pd
import ta

def generate_signal(df: pd.DataFrame, mode: str = "scalp"):
    """
    df must contain columns: open, high, low, close, volume
    """

    # === ATR for volatility ===
    atr = ta.volatility.AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14,
    ).average_true_range()

    df = df.copy()
    df["atr"] = atr

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # === Basic Structure (example: Break of Structure) ===
    if last["close"] > df["high"].rolling(20).max().iloc[-2]:
        side = "buy"
    elif last["close"] < df["low"].rolling(20).min().iloc[-2]:
        side = "sell"
    else:
        return None

    # === Entry Zone (Hybrid) ===
    structure_low = prev["low"]
    structure_high = prev["high"]

    pad = last["atr"] * (0.25 if mode == "scalp" else 0.5)

    entry_min = structure_low - pad
    entry_max = structure_high + pad
    entry_mid = (entry_min + entry_max) / 2

    # === SL ===
    if side == "buy":
        sl = structure_low - last["atr"] * 0.5
    else:
        sl = structure_high + last["atr"] * 0.5

    risk = abs(entry_mid - sl)

    # === TP Ladder ===
    tp1 = entry_mid + risk * (1 if side == "buy" else -1)
    tp2 = entry_mid + risk * (2 if side == "buy" else -2)
    tp3 = entry_mid + risk * (3 if side == "buy" else -3)

    return {
        "side": side,
        "entry_min": round(entry_min, 4),
        "entry_max": round(entry_max, 4),
        "entry_mid": round(entry_mid, 4),
        "sl": round(sl, 4),
        "tp1": round(tp1, 4),
        "tp2": round(tp2, 4),
        "tp3": round(tp3, 4),
    }