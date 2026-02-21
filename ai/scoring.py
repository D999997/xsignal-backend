# ai/scoring.py
from __future__ import annotations

import numpy as np
import pandas as pd
import ta


# -----------------------------
# Helpers
# -----------------------------
def _clamp01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def _safe_last(s: pd.Series, default: float = 0.0) -> float:
    try:
        v = float(s.iloc[-1])
        if np.isnan(v) or np.isinf(v):
            return default
        return v
    except Exception:
        return default


def _normalize_from_range(x: float, lo: float, hi: float) -> float:
    """Map x from [lo..hi] to [0..1] and clamp."""
    if hi <= lo:
        return 0.0
    return _clamp01((x - lo) / (hi - lo))


# -----------------------------
# Feature extraction (per timeframe df)
# Returns values in 0..1
# -----------------------------
def extract_features(df: pd.DataFrame) -> dict:
    """
    df must contain: open, high, low, close, volume
    Returns a bundle:
      structure_strength: 0..1
      trend_strength: 0..1
      momentum: 0..1
      volatility: 0..1
      explain: raw values (optional)
    """
    d = df.copy()

    # ---- Indicators ----
    # ATR (volatility)
    atr = ta.volatility.AverageTrueRange(
        high=d["high"], low=d["low"], close=d["close"], window=14
    ).average_true_range()

    # EMA trend
    ema_fast = ta.trend.EMAIndicator(close=d["close"], window=20).ema_indicator()
    ema_slow = ta.trend.EMAIndicator(close=d["close"], window=50).ema_indicator()

    # ADX (trend strength)
    adx = ta.trend.ADXIndicator(
        high=d["high"], low=d["low"], close=d["close"], window=14
    ).adx()

    # RSI (momentum)
    rsi = ta.momentum.RSIIndicator(close=d["close"], window=14).rsi()

    # Volume spike vs SMA
    vol_sma = d["volume"].rolling(20).mean()

    # ---- Raw last values ----
    last_close = float(d["close"].iloc[-1])
    last_atr = _safe_last(atr, 0.0)
    last_ema_fast = _safe_last(ema_fast, last_close)
    last_ema_slow = _safe_last(ema_slow, last_close)
    last_adx = _safe_last(adx, 0.0)
    last_rsi = _safe_last(rsi, 50.0)
    last_vol = float(d["volume"].iloc[-1])
    last_vol_sma = float(vol_sma.iloc[-1]) if len(vol_sma) and not np.isnan(vol_sma.iloc[-1]) else last_vol

    # -----------------------------
    # 1) Structure strength (0..1)
    # -----------------------------
    # We approximate "structure" by:
    # - breakout proximity (close vs 20-period high/low)
    # - volume confirmation (volume vs vol_sma)
    hh20_prev = d["high"].rolling(20).max().iloc[-2] if len(d) >= 22 else float(d["high"].max())
    ll20_prev = d["low"].rolling(20).min().iloc[-2] if len(d) >= 22 else float(d["low"].min())

    # breakout distance: if close is beyond prior HH/LL -> stronger
    # We map within +/- 0.5% range as a smooth score
    # (You can tune these thresholds)
    if hh20_prev > 0:
        above_hh = (last_close - hh20_prev) / hh20_prev
    else:
        above_hh = 0.0
    if ll20_prev > 0:
        below_ll = (ll20_prev - last_close) / ll20_prev
    else:
        below_ll = 0.0

    breakout_raw = max(above_hh, below_ll)  # positive if breakout
    breakout_score = _normalize_from_range(breakout_raw, 0.0, 0.005)  # 0%..0.5%

    # volume confirmation
    vol_ratio = (last_vol / last_vol_sma) if last_vol_sma > 0 else 1.0
    vol_score = _normalize_from_range(vol_ratio, 0.8, 1.8)  # 0.8x..1.8x

    structure_strength = _clamp01(0.65 * breakout_score + 0.35 * vol_score)

    # -----------------------------
    # 2) Trend strength (0..1)
    # -----------------------------
    # Combine:
    # - ADX normalized (10..35 typical)
    # - EMA alignment & separation (fast vs slow)
    adx_score = _normalize_from_range(last_adx, 10.0, 35.0)

    # EMA separation vs price (bigger separation => clearer trend)
    ema_sep = abs(last_ema_fast - last_ema_slow)
    sep_ratio = (ema_sep / last_close) if last_close > 0 else 0.0
    sep_score = _normalize_from_range(sep_ratio, 0.0, 0.01)  # 0%..1%

    # Alignment: fast above slow = trending (either direction still trend, so use abs slope proxy)
    # Use signless alignment confidence by how far apart they are (sep_score already captures)
    trend_strength = _clamp01(0.7 * adx_score + 0.3 * sep_score)

    # -----------------------------
    # 3) Momentum (0..1)
    # -----------------------------
    # Use RSI distance from 50.
    # RSI 50 => 0, RSI 70 or 30 => 1
    momentum = _clamp01(abs(last_rsi - 50.0) / 20.0)

    # -----------------------------
    # 4) Volatility (0..1)
    # -----------------------------
    # We want "healthy" volatility (not too low).
    # Use ATR% of price.
    atr_pct = (last_atr / last_close) if last_close > 0 else 0.0
    volatility = _normalize_from_range(atr_pct, 0.0015, 0.01)  # 0.15%..1.0%

    return {
        "structure_strength": structure_strength,
        "trend_strength": trend_strength,
        "momentum": momentum,
        "volatility": volatility,
        "explain": {
            "breakout_score": breakout_score,
            "vol_score": vol_score,
            "adx": last_adx,
            "adx_score": adx_score,
            "ema_sep_ratio": sep_ratio,
            "sep_score": sep_score,
            "rsi": last_rsi,
            "atr_pct": atr_pct,
            "vol_ratio": vol_ratio,
        },
    }


# -----------------------------
# Step 41.4 — Real Xscore
# -----------------------------
def calculate_xscore(features_bundle: dict) -> int:
    """
    Weighted score based on real features.
    Expected bundle keys: f5, f15, f1h
    """
    f5 = features_bundle["f5"]
    f15 = features_bundle["f15"]
    f1h = features_bundle["f1h"]

    # weights: structure (35), trend (35), momentum (20), volatility (10)
    structure = f5["structure_strength"]  # 0..1
    trend = (f15["trend_strength"] * 0.6 + f1h["trend_strength"] * 0.4)
    momentum = f5["momentum"]
    volatility = f5["volatility"]

    score = (
        structure * 35 +
        trend * 35 +
        momentum * 20 +
        volatility * 10
    )

    return int(np.clip(score, 0, 100))


def confidence_text(xscore: int) -> str:
    if xscore >= 75:
        return "VERY HIGH"
    if xscore >= 60:
        return "HIGH"
    if xscore >= 45:
        return "MEDIUM"
    return "LOW"


def score_signal(df5: pd.DataFrame, df15: pd.DataFrame, df1h: pd.DataFrame, sig: dict) -> dict:
    """
    Attach explainable Xscore + breakdown to the signal.
    """
    f5 = extract_features(df5)
    f15 = extract_features(df15)
    f1h = extract_features(df1h)

    bundle = {"f5": f5, "f15": f15, "f1h": f1h}
    xscore = calculate_xscore(bundle)

    # Explainable contributions (0..points)
    structure_pts = f5["structure_strength"] * 35
    trend_pts = (f15["trend_strength"] * 0.6 + f1h["trend_strength"] * 0.4) * 35
    momentum_pts = f5["momentum"] * 20
    volatility_pts = f5["volatility"] * 10

    out = dict(sig)
    out["confidence"] = xscore
    out["confidence_text"] = confidence_text(xscore)

    # ✅ Explainability payload
    out["xscore_breakdown"] = {
        "structure": round(structure_pts, 2),
        "trend": round(trend_pts, 2),
        "momentum": round(momentum_pts, 2),
        "volatility": round(volatility_pts, 2),
        "total": xscore,
    }

    # Optional: include raw indicator info (debug)
    out["xscore_features"] = {
        "f5": {
            "structure_strength": round(f5["structure_strength"], 4),
            "trend_strength": round(f5["trend_strength"], 4),
            "momentum": round(f5["momentum"], 4),
            "volatility": round(f5["volatility"], 4),
        },
        "f15": {
            "trend_strength": round(f15["trend_strength"], 4),
        },
        "f1h": {
            "trend_strength": round(f1h["trend_strength"], 4),
        },
    }

    return out