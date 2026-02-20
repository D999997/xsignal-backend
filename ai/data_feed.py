import requests
import pandas as pd

BINANCE_BASE = "https://api.binance.com"

def fetch_ohlcv_binance(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    url = f"{BINANCE_BASE}/api/v3/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    df = pd.DataFrame(
        data,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "num_trades", "tbbav", "tbqav", "ignore"
        ],
    )
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df