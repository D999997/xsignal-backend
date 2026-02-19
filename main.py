from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime, timezone
import uuid

app = FastAPI(title="Xsignal AI Backend", version="0.2.0")

class GenerateSignalRequest(BaseModel):
    symbol: str
    mode: Literal["scalp", "swing"]
    timeframe: str
    market: Optional[str] = "forex"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "Xsignal backend running"}

@app.post("/signals/generate")
def generate(req: GenerateSignalRequest):
    try:
        signal_id = str(uuid.uuid4())

        return {
            "id": signal_id,
            "symbol": req.symbol.upper(),
            "mode": req.mode,
            "timeframe": req.timeframe,
            "market": req.market,
            "side": "buy",
            "entryMin": 100,
            "entryMax": 101,
            "sl": 98,
            "tp1": 102,
            "tp2": 103,
            "tp3": 104,
            "xscore": 75,
            "riskGrade": "B+",
            "rr": 2.5,
            "marketMood": "Neutral",
            "tradeType": "Breakout",
            "status": "active",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))