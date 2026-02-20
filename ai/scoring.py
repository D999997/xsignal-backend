import numpy as np


def calculate_xscore(structure_strength, momentum, volatility):
    """
    Inputs between 0-1
    """

    score = (
        structure_strength * 40 +
        momentum * 35 +
        volatility * 25
    )

    return int(np.clip(score, 0, 100))


def score_signal(sig: dict) -> dict:
    """
    Wrap raw signal and attach confidence score.
    """

    # Simple placeholder logic (you can improve later)
    structure_strength = 0.7
    momentum = 0.65
    volatility = 0.6

    xscore = calculate_xscore(
        structure_strength,
        momentum,
        volatility
    )

    sig = dict(sig)
    sig["confidence"] = xscore

    if xscore >= 75:
        sig["confidence_text"] = "VERY HIGH"
    elif xscore >= 60:
        sig["confidence_text"] = "HIGH"
    elif xscore >= 45:
        sig["confidence_text"] = "MEDIUM"
    else:
        sig["confidence_text"] = "LOW"

    return sig