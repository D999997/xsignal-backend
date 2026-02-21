# ai/tier_router.py
from __future__ import annotations

def tier_from_xscore(xscore: int, cfg: dict) -> str:
    """
    Decide which tier receives this signal.
    Safe against missing or malformed config.
    """

    try:
        min_free = int(cfg.get("min_xscore_free", 55))
        min_pro = int(cfg.get("min_xscore_pro", 70))
        min_xpro = int(cfg.get("min_xscore_xpro", 85))
    except Exception:
        # fallback defaults if config corrupted
        min_free, min_pro, min_xpro = 55, 70, 85

    if xscore >= min_xpro:
        return "xpro"

    if xscore >= min_pro:
        return "pro"

    if xscore >= min_free:
        return "free"

    return "reject"