from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone
import uuid
import os
import pandas as pd

# Firebase (optional)
db = None
firestore = None

def init_firestore():
    """Initialize Firestore if firebase_admin.json exists and valid."""
    global db, firestore
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore as _firestore

        firestore = _firestore

        if firebase_admin._apps:
            db = _firestore.client()
            return

        if not os.path.exists("firebase_admin.json"):
            print("⚠️ firebase_admin.json not found. Scheduler publish disabled.")
            db = None
            return

        if os.path.getsize("firebase_admin.json") < 50:
            print("⚠️ firebase_admin.json looks empty. Scheduler publish disabled.")
            db = None
            return

        cred = credentials.Certificate("firebase_admin.json")
        firebase_admin.initialize_app(cred)
        db = _firestore.client()
        print("✅ Scheduler Firestore ready")
    except Exception as e:
        print(f"⚠️ Scheduler Firestore init failed: {e}")
        db = None

# ---- AI modules ----
from ai.signal_engine import generate_signal
from ai.scoring import score_signal

scheduler = BackgroundScheduler()
_started = False


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Simple ATR implementation (no external TA dependency)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.rolling(period).mean()
    return atr


def scan_market(pair: str, mode: str, timeframe: str, market: str = "forex"):
    """
    Auto-scan + publish a signal.
    Includes:
      - Spam protection (no buy/buy repetition)
      - Volatility filter (ATR too low -> skip)
    """
    # ---- 0) Load market data (TEMP DEMO) ----
    # Replace this later with real OHLC fetcher
    # For now, if sample_data.csv exists, use it; otherwise skip.
    if not os.path.exists("sample_data.csv"):
        print("⚠️ sample_data.csv not found; skipping scan.")
        return

    df = pd.read_csv("sample_data.csv")

    # Require columns for ATR
    required_cols = {"high", "low", "close"}
    if not required_cols.issubset(set(df.columns)):
        print("⚠️ sample_data.csv must contain high, low, close columns.")
        return

    # ---- 1) ATR + Volatility Filter (STEP 39.5) ----
    df["atr"] = compute_atr(df, period=14)

    if df["atr"].dropna().empty:
        print("⚠️ ATR not ready yet; skipping.")
        return

    atr_now = df["atr"].iloc[-1]
    atr_mean = df["atr"].rolling(50).mean().iloc[-1]

    # market too quiet
    if pd.notna(atr_mean) and atr_now < atr_mean * 0.7:
        print("😴 Volatility too low, skipping signal.")
        return

    # ---- 2) Generate signal ----
    sig = generate_signal(
        symbol=pair,
        timeframe=timeframe,
        mode=mode,
        market=market,
    )
    if not sig:
        print("❌ No signal found.")
        return

    sig = score_signal(sig)

    # ---- 3) Spam protection (STEP 39.4) ----
    # Only works if Firestore enabled
    if db is not None and firestore is not None:
        try:
            recent = (
                db.collection("signals")
                .where("symbol", "==", pair)
                .where("mode", "==", mode)
                .order_by("createdAt", direction=firestore.Query.DESCENDING)
                .limit(1)
                .stream()
            )
            recent_list = list(recent)

            if recent_list:
                last_signal = recent_list[0].to_dict()
                if last_signal.get("side") == sig.get("side"):
                    print("🛑 Spam protection: same side as last signal. Skipping.")
                    return
        except Exception as e:
            print(f"⚠️ Spam check failed (continuing anyway): {e}")

    # ---- 4) Build payload + publish ----
    signal_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "id": signal_id,
        "symbol": pair,
        "mode": mode,
        "timeframe": timeframe,
        "market": market,
        "tier": "pro",
        "status": "active",
        "createdAt": now,
        **sig,
    }

    # Publish to Firestore if enabled
    if db is not None:
        try:
            db.collection("signals").document(signal_id).set(payload)
            print("✅ Published signal:", payload["id"], payload["symbol"], payload["side"])
        except Exception as e:
            print(f"❌ Publish failed: {e}")
    else:
        # If no Firestore, just log
        print("🟡 Firestore disabled. Signal generated:", payload)


def start_scheduler():
    global _started
    if _started:
        return

    init_firestore()

    # Demo schedule: every 60 seconds.
    # Later: scalp every 5m, swing every 30m.
    scheduler.add_job(
        scan_market,
        "interval",
        seconds=60,
        kwargs={"pair": "XAUUSD", "mode": "scalp", "timeframe": "5m", "market": "forex"},
        id="scan_xauusd_scalp",
        replace_existing=True,
    )

    scheduler.start()
    _started = True
    print("🟢 Scheduler started (auto-scan enabled)")