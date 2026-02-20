# =========================
# main.py (AUTO TIMEFRAME + TEST OHLCV)
# =========================
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime, timezone
import uuid
import os

# --- AI modules ---
from ai.signal_engine import generate_signal
from ai.scoring import score_signal

# ✅ Scheduler
from ai.scheduler import start_scheduler

# ✅ Data feed (Binance)
from ai.data_feed import fetch_ohlcv_binance

app = FastAPI(title="Xsignal AI Backend", version="0.3.4")


# ---------------------------
# Firebase (optional)
# ---------------------------
db = None

def _init_firebase():
    """
    Priority:
    1) Railway env var: FIREBASE_CREDENTIALS_JSON (prod)
    2) Local file: firebase_admin.json (dev)
    """
    global db
    try:
        import json
        import firebase_admin
        from firebase_admin import credentials, firestore

        if firebase_admin._apps:
            db = firestore.client()
            return

        firebase_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")

        if firebase_json and len(firebase_json) > 50:
            cred = credentials.Certificate(json.loads(firebase_json))
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("✅ Firebase Admin initialized (env)")
            return

        if os.path.exists("firebase_admin.json") and os.path.getsize("firebase_admin.json") > 50:
            cred = credentials.Certificate("firebase_admin.json")
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("✅ Firebase Admin initialized (file)")
            return

        print("⚠️ Firebase credentials not found. Firestore disabled.")
        db = None

    except Exception as e:
        print(f"⚠️ Firebase init failed. Firestore disabled. Reason: {e}")
        db = None

_init_firebase()


@app.on_event("startup")
def startup_event():
    # If you don’t want scheduler in dev, you can comment this line.
    start_scheduler()


# ---------------------------
# Request model
# ---------------------------
class GenerateSignalRequest(BaseModel):
    symbol: str
    mode: Literal["scalp", "swing"]
    timeframe: Optional[str] = None  # optional now
    market: Optional[str] = "crypto"
    tier: Optional[str] = "pro"


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root():
    return {"message": "Xsignal backend running"}


# ✅ Step 40.6 — Manual OHLCV test endpoint
@app.get("/test_ohlcv")
def test_ohlcv(pair: str = "BTCUSDT", timeframe: str = "5m"):
    try:
        df = fetch_ohlcv_binance(symbol=pair, interval=timeframe, limit=50)
        last = df.iloc[-1].to_dict() if len(df) > 0 else None
        return {
            "pair": pair,
            "timeframe": timeframe,
            "rows": len(df),
            "last": last,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.post("/signals/generate")
def signals_generate(req: GenerateSignalRequest):
    try:
        # ✅ Step 40.4 — auto timeframe by mode (if not provided)
        tf = req.timeframe or ("5m" if req.mode == "scalp" else "1h")

        # 1) Fetch candles
        df = fetch_ohlcv_binance(symbol=req.symbol, interval=tf, limit=200)

        # 2) Generate signal
        raw = generate_signal(df, mode=req.mode)
        if raw is None:
            return {"status": "no_signal", "reason": "No breakout / BOS trigger"}

        # 3) Score
        sig = score_signal(raw)

        signal_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "id": signal_id,
            "symbol": req.symbol.upper(),
            "mode": req.mode,
            "timeframe": tf,
            "market": req.market,
            "tier": req.tier,
            "status": "active",
            "createdAt": now,
            **sig,
        }

        # 4) Store in Firestore if enabled
        if db is not None:
            db.collection("signals").document(signal_id).set(payload)

        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")