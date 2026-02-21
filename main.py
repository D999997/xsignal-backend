# =========================
# main.py (MULTI-TF + KILL SWITCH + TIER ROUTING)
# =========================
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime, timezone
import uuid
import os

# --- AI modules ---
from ai.signal_engine import generate_signal

# ✅ Multi-TF + Xscore + tier routing + config
from ai.multi_tf import multi_tf_confirm
from ai.scoring import calculate_xscore
from ai.tier_router import tier_from_xscore
from ai.config import load_engine_config

# ✅ Scheduler
from ai.scheduler import start_scheduler

# ✅ Data feed (Binance)
from ai.data_feed import fetch_ohlcv_binance

app = FastAPI(title="Xsignal AI Backend", version="0.3.5")


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


# ✅ Initialize Firebase before startup event
_init_firebase()


@app.on_event("startup")
def startup_event():
    # Scheduler will safely handle Firestore not initialized
    start_scheduler()


# ---------------------------
# Request model
# ---------------------------
class GenerateSignalRequest(BaseModel):
    symbol: str
    mode: Literal["scalp", "swing"]
    timeframe: Optional[str] = None  # optional; will auto-set from mode
    market: Optional[str] = "crypto"
    tier: Optional[str] = "pro"      # used only for display; routing uses cfg thresholds


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root():
    return {"message": "Xsignal backend running"}


# ✅ Manual OHLCV test endpoint
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


def _confidence_text(x: int) -> str:
    if x >= 75:
        return "VERY HIGH"
    if x >= 60:
        return "HIGH"
    if x >= 45:
        return "MEDIUM"
    return "LOW"


@app.post("/signals/generate")
def signals_generate(req: GenerateSignalRequest):
    """
    ✅ Option B:
    - Kill switch + pairs allowlist from Firestore config
    - Multi-TF confirm (f5/f15/f1h) => side + features bundle
    - Xscore from real features => calculate_xscore(bundle)
    - Tier routing (free/pro/xpro/reject) using cfg thresholds
    - Generate entry/SL/TP using mode timeframe df
    - Force signal side to match multi-TF side
    """
    try:
        symbol = req.symbol.upper().strip()

        # ✅ Load config (kill switch + thresholds + pairs)
        cfg = load_engine_config()

        # Kill switch
        if not cfg.get("enabled", True):
            raise HTTPException(status_code=503, detail="Signal engine disabled")

        # Pair allowlist
        allowed_pairs = [p.upper().strip() for p in (cfg.get("pairs") or [])]
        if allowed_pairs and symbol not in set(allowed_pairs):
            raise HTTPException(status_code=400, detail=f"Pair not allowed: {symbol}")

        # ✅ Multi-TF confirm defines side + features bundle
        ok, side, feats = multi_tf_confirm(symbol)
        if not ok:
            return {"status": "no_signal", "reason": "multi_tf_confirm failed"}

        # ✅ Real Xscore (0..100)
        xscore = calculate_xscore(feats)

        # ✅ Tier routing from config thresholds
        routed_tier = tier_from_xscore(xscore, cfg)
        if routed_tier == "reject":
            return {
                "status": "no_signal",
                "reason": "xscore below thresholds",
                "xscore": xscore,
            }

        # ✅ Auto timeframe by mode (or user override)
        tf = req.timeframe or ("5m" if req.mode == "scalp" else "1h")

        # ✅ Fetch DF for entry/SL/TP generation
        df = fetch_ohlcv_binance(symbol=symbol, interval=tf, limit=200)

        # ✅ Generate raw signal from df
        raw = generate_signal(df, mode=req.mode)
        if raw is None:
            return {"status": "no_signal", "reason": "No breakout / BOS trigger"}

        # ✅ Force side to match multi-TF side
        if raw.get("side") != side:
            return {"status": "no_signal", "reason": "side mismatch multiTF"}

        # ✅ Attach explainable scoring outputs
        sig = dict(raw)
        sig["confidence"] = xscore
        sig["confidence_text"] = _confidence_text(xscore)

        # Optional: include features bundle (you can remove later for free users)
        sig["xscore_features"] = feats
        sig["tier_routed"] = routed_tier

        signal_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "id": signal_id,
            "symbol": symbol,
            "mode": req.mode,
            "timeframe": tf,
            "market": req.market,
            # keep what user sent + what system routed (both useful for debugging)
            "tier_requested": (req.tier or "pro"),
            "tier": routed_tier,
            "status": "active",
            "createdAt": now,
            **sig,
        }

        # ✅ Store in Firestore if enabled
        if db is not None:
            db.collection("signals").document(signal_id).set(payload)

        return payload

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")