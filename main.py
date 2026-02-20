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

app = FastAPI(title="Xsignal AI Backend", version="0.3.0")

# ---------------------------
# Firebase (optional)
# ---------------------------
db = None

def _init_firebase():
    """
    Priority:
    1) Railway env var: FIREBASE_CREDENTIALS_JSON  (recommended for production)
    2) Local file: firebase_admin.json             (optional for local dev)
    """
    global db
    try:
        import json
        import firebase_admin
        from firebase_admin import credentials, firestore

        # If already initialized, just grab Firestore client
        if firebase_admin._apps:
            db = firestore.client()
            return

        firebase_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")

        # ✅ 1) Production (Railway): use env var JSON
        if firebase_json and len(firebase_json) > 50:
            cred = credentials.Certificate(json.loads(firebase_json))
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("✅ Firebase Admin initialized (env)")
            return

        # ✅ 2) Local dev fallback: use file if it exists
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

# ✅ Start scheduler when server starts
@app.on_event("startup")
def startup_event():
    start_scheduler()

# ---------------------------
# Request model
# ---------------------------
class GenerateSignalRequest(BaseModel):
    symbol: str
    mode: Literal["scalp", "swing"]
    timeframe: str
    market: Optional[str] = "forex"
    tier: Optional[str] = "pro"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "Xsignal backend running"}

@app.post("/signals/generate")
def signals_generate(req: GenerateSignalRequest):
    try:
        sig = generate_signal(
            symbol=req.symbol,
            timeframe=req.timeframe,
            mode=req.mode,
            market=req.market or "forex",
        )

        sig = score_signal(sig)

        signal_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "id": signal_id,
            "symbol": req.symbol.upper(),
            "mode": req.mode,
            "timeframe": req.timeframe,
            "market": req.market,
            "tier": req.tier,
            "status": "active",
            "createdAt": now,
            **sig,
        }

        if db is not None:
            db.collection("signals").document(signal_id).set(payload)

        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
