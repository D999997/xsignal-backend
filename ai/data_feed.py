import time
import requests
import pandas as pd

# Try vision first (less blocked), then main API
BINANCE_URLS = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
]

# Map your app timeframes -> Binance intervals
TF_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "1d": "1d",
}


def fetch_ohlcv_binance(symbol: str, interval: str = "5m", limit: int = 200) -> pd.DataFrame:
    """
    Fetch OHLCV candles from Binance public endpoint.
    Returns DataFrame with columns: open, high, low, close, volume
    """

    interval = TF_MAP.get(interval, interval)
    last_err = None

    for base in BINANCE_URLS:
        try:
            url = f"{base}/api/v3/klines"
            params = {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": limit,
            }

            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            }

            r = requests.get(url, params=params, headers=headers, timeout=20)

            if r.status_code != 200:
                raise RuntimeError(
                    f"Binance HTTP {r.status_code} from {base}: {r.text[:200]}"
                )

            data = r.json()

            df = pd.DataFrame(
                data,
                columns=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "qav", "num_trades", "tbbav", "tbqav", "ignore",
                ],
            )

            df = df[["open", "high", "low", "close", "volume"]].astype(float)

            return df

        except Exception as e:
            last_err = e

    raise RuntimeError(
        f"Failed to fetch Binance candles from all endpoints: {last_err}"
    )


# Optional: simple rate-limit safety
def safe_fetch(symbol: str, interval: str, limit: int = 200, sleep_s: float = 0.2) -> pd.DataFrame:
    time.sleep(sleep_s)
    return fetch_ohlcv_binance(symbol, interval, limit)