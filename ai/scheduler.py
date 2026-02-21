# ai/scheduler.py
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

# ✅ Needed for SERVER_TIMESTAMP in queue writes
from firebase_admin import firestore

# AI
from ai.signal_engine import generate_signal
from ai.multi_tf import multi_tf_confirm
from ai.scoring import calculate_xscore
from ai.tier_router import tier_from_xscore
from ai.config import load_engine_config  # <-- your file name from earlier
from ai.data_feed import safe_fetch  # <-- keep your safe_fetch wrapper

# Firestore (optional)
db = None
firestore_mod = None

scheduler = BackgroundScheduler()


def _try_init_firestore():
    """
    Scheduler must not crash if Firebase isn't initialized.
    main.py should initialize firebase_admin.
    """
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
    """
    Block publishing if last QUEUED signal is same pair+mode+side.
    (We check signal_queue pending docs to prevent spam.)
    """
    if db is None or firestore_mod is None:
        return False

    try:
        recent = (
            db.collection("signal_queue")
            .where("pair", "==", pair)
            .where("mode", "==", mode)
            .where("status", "==", "pending")
            .order_by("createdAt", direction=firestore_mod.Query.DESCENDING)
            .limit(1)
            .stream()
        )

        recent_list = list(recent)
        if not recent_list:
            return False

        last_signal = recent_list[0].to_dict()
        return (last_signal.get("side") == side)
    except Exception as e:
        print(f"⚠️ Spam check failed: {e}")
        return False


def publish_signal(
    pair: str,
    mode: str,
    side: str,
    xscore: int,
    signal: dict,
    features: dict,
    tier: str,
):
    """
    ✅ Queue-first publishing (trust model):
    Save into signal_queue with status=pending.
    Admin approves -> move to signals.
    """
    signal_data = {
        "pair": pair,
        "mode": mode,
        "tier": tier,
        "side": side,
        "xscore": xscore,
        # keep createdAt here for local/logging, but we override with SERVER_TIMESTAMP at write time
        "createdAt": (firestore_mod.SERVER_TIMESTAMP if firestore_mod else None),
        "features": features,  # optional: later hide from free users
        **signal,
    }

    if db is None:
        print(f"[SIGNAL] {pair} {mode} {side} tier={tier} xscore={xscore} (not saved: no firestore)")
        return

    try:
        db.collection("signal_queue").add({
            **signal_data,
            "status": "pending",
            "createdAt": firestore.SERVER_TIMESTAMP,
        })
        print(f"[QUEUED] {pair} {mode} {side} tier={tier} xscore={xscore} (pending)")
    except Exception as e:
        print(f"⚠️ Queue write failed: {e}")


def scan_pair(pair: str, mode: str):
    """
    Full pipeline:
    - load config (kill switch + pairs)
    - multi-TF confirm (returns side + features bundle)
    - xscore from features
    - tier routing from xscore + cfg thresholds
    - generate entries/SL/TP with generate_signal on mode TF
    - force side match + spam block
    - queue (pending)
    """
    cfg = load_engine_config()

    # ✅ Kill switch
    if not cfg.get("enabled", True):
        print("[ENGINE OFF] Kill switch enabled")
        return

    pair = pair.upper().strip()

    # ✅ Pair allowlist (defensive)
    allowed_pairs = [p.upper().strip() for p in (cfg.get("pairs") or [])]
    if allowed_pairs and pair not in set(allowed_pairs):
        return

    # ✅ Multi-TF confirm defines side + features bundle
    ok, side, feats = multi_tf_confirm(pair)
    if not ok:
        return

    # ✅ Real Xscore (0..100) from features bundle {f5,f15,f1h}
    try:
        xscore = calculate_xscore(feats)
    except Exception as e:
        print(f"⚠️ Xscore calc failed for {pair}: {e}")
        return

    # ✅ Route tier based on thresholds in config
    tier = tier_from_xscore(xscore, cfg)
    if tier == "reject":
        return

    # ✅ Fetch DF for entry/SL/TP generation (use mode timeframe)
    tf = "5m" if mode == "scalp" else "1h"
    df = safe_fetch(pair, tf, limit=300)

    signal = generate_signal(df, mode)
    if not signal:
        return

    # Force signal side to match multi-tf side (very important)
    if signal.get("side") != side:
        return

    # ✅ Spam block: don’t repeat same direction while pending
    if should_spam_block(pair, mode, side):
        return

    publish_signal(pair, mode, side, xscore, signal, feats, tier)


def start_scheduler():
    """
    Called from main.py startup.
    Scheduler uses Firestore config live each run.
    """
    _try_init_firestore()

    def scalp_job():
        cfg = load_engine_config()
        for p in (cfg.get("pairs") or []):
            scan_pair(p, "scalp")

    def swing_job():
        cfg = load_engine_config()
        for p in (cfg.get("pairs") or []):
            scan_pair(p, "swing")

    scheduler.add_job(
        scalp_job,
        "interval",
        minutes=5,
        id="scan_scalp",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        swing_job,
        "interval",
        hours=1,
        id="scan_swing",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    print("✅ Scheduler started (multi-TF + kill switch + tier routing) — queue-first enabled")