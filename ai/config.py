# ai/config.py
from __future__ import annotations

DEFAULTS = {
    "enabled": True,
    "min_xscore_free": 55,
    "min_xscore_pro": 70,
    "min_xscore_xpro": 85,
    "pairs": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
}

def load_engine_config():
    """
    Safe loader:
    - If firebase_admin is not initialized yet -> return DEFAULTS (no crash)
    - If initialized -> read /config/signal_engine
    - If doc missing -> create it
    """
    try:
        import firebase_admin
        from firebase_admin import firestore

        # ✅ If Firebase not initialized yet, don't crash app import
        if not firebase_admin._apps:
            return DEFAULTS

        db = firestore.client()
        ref = db.collection("config").document("signal_engine")
        doc = ref.get()

        if not doc.exists:
            ref.set(DEFAULTS, merge=True)
            return DEFAULTS

        data = doc.to_dict() or {}
        return {**DEFAULTS, **data}

    except Exception as e:
        print(f"⚠️ load_engine_config failed: {e}")
        return DEFAULTS