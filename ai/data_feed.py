import requests
import pandas as pd

BINANCE_URLS = [
    "https://data-api.binance.vision",  # ✅ usually works where api.binance.com is blocked
    "https://api.binance.com",          # fallback
]

def fetch_ohlcv_binance(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    last_err = None

    for base in BINANCE_URLS:
        try:
            url = f"{base}/api/v3/klines"
            params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            }

            r = requests.get(url, params=params, headers=headers, timeout=20)

            if r.status_code != 200:
                raise RuntimeError(f"Binance HTTP {r.status_code} from {base}: {r.text[:200]}")

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

        except Exception as e:
            last_err = e

    raise RuntimeError(f"Failed to fetch Binance candles from all endpoints: {last_err}")