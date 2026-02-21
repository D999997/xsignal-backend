# ai/scheduler.py
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from ai.signal_engine import generate_signal
from ai.multi_tf import multi_tf_confirm
from ai.scoring import calculate_xscore
from ai.tier_router import tier_from_xscore
from ai.config import load_engine_config
from ai.data_feed import fetch_ohlcv_binance  # ✅ use your real OHLC fetcher

# Firestore optional
db = None
firestore_mod = None

scheduler = BackgroundScheduler()
_started = False


def _try_init_firestore():
    global db, firestore_mod
    try:
        import firebase_admin
        from firebase_admin import firestore as fs

        firestore_mod = fs

        if not firebase_admin._apps:
            print("⚠️ Scheduler: Firebase not initialized yet. Firestore disabled for scheduler.")
            db = None
            return

        db = fs.client()
        print("✅ Scheduler: Firestore client ready")
    except Exception as e:
        print(f"⚠️ Scheduler: Firestore unavailable ({e}). Scheduler will run without saving.")
        db = None


def should_spam_block(pair: str, mode: str, side: str) -> bool:
    if db is None or firestore_mod is None:
        return False

    try:
        recent = (
            db.collection("signals")
            .where("pair", "==", pair)
            .where("mode", "==", mode)
            .order_by("createdAt", direction=firestore_mod.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        recent_list = list(recent)
        if not recent_list:
            return False

        last_signal = recent_list[0].to_dict()
        return last_signal.get("side") == side
    except Exception as e:
        print(f"⚠️ Spam check failed: {e}")
        return False


def publish_signal(pair: str, mode: str, side: str, xscore: int, signal: dict, features: dict, tier: str):
    payload = {
        "pair": pair,
        "mode": mode,
        "tier": tier,
        "side": side,
        "xscore": xscore,
        "createdAt": (firestore_mod.SERVER_TIMESTAMP if firestore_mod else None),
        "features": features,
        **signal,
    }

    if db is None:
        print(f"[SIGNAL] {pair} {mode} {side} tier={tier} xscore={xscore} (not saved: no firestore)")
        return

    try:
        db.collection("signals").add(payload)
        print(f"[PUBLISHED] {pair} {mode} {side} tier={tier} xscore={xscore}")
    except Exception as e:
        print(f"⚠️ Publish failed: {e}")


def scan_pair(pair: str, mode: str):
    cfg = load_engine_config()

    # ✅ Kill switch
    if not cfg.get("enabled", True):
        print("[ENGINE OFF] Kill switch enabled")
        return

    pair = pair.upper().strip()

    # ✅ Pair allowlist
    allowed = [p.upper().strip() for p in (cfg.get("pairs") or [])]
    if allowed and pair not in set(allowed):
        return

    # ✅ Multi-TF confirm => (ok, side, feats_bundle)
    ok, side, feats = multi_tf_confirm(pair)
    if not ok:
        return

    # ✅ Real xscore from features bundle
    try:
        xscore = calculate_xscore(feats)   # feats must include f5,f15,f1h
    except Exception as e:
        print(f"⚠️ Xscore calc failed for {pair}: {e}")
        return

    # ✅ Tier routing (reject / free / pro / xpro)
    tier = tier_from_xscore(xscore, cfg)
    if tier == "reject":
        return

    # ✅ Generate entry/SL/TP from the mode timeframe df
    tf = "5m" if mode == "scalp" else "1h"
    df = fetch_ohlcv_binance(pair, tf, 300)

    signal = generate_signal(df, mode)
    if not signal:
        return

    # Force side to match multi-tf side
    if signal.get("side") != side:
        return

    # ✅ Spam block
    if should_spam_block(pair, mode, side):
        return

    publish_signal(pair, mode, side, xscore, signal, feats, tier)


def start_scheduler():
    global _started
    if _started:
        return

    _try_init_firestore()

    def scalp_job():
        cfg = load_engine_config()
        for p in (cfg.get("pairs") or []):
            scan_pair(p, "scalp")

    def swing_job():
        cfg = load_engine_config()
        for p in (cfg.get("pairs") or []):
            scan_pair(p, "swing")

    scheduler.add_job(scalp_job, "interval", minutes=5, id="scan_scalp", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(swing_job, "interval", hours=1, id="scan_swing", replace_existing=True, max_instances=1, coalesce=True)

    scheduler.start()
    _started = True
    print("✅ Scheduler started (multi-TF + kill switch + tier routing)")