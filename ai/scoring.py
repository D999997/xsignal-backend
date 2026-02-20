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