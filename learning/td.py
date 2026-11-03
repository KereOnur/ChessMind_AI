"""Bounded TD(0) with a fixed White perspective and five coefficients."""
from dataclasses import dataclass
import math

NAMES = ('Figurenaktivität', 'Zentrumskontrolle', 'Königssicherheit',
         'Bauernstruktur', 'Endspielstrategie')
INITIAL = (1.0,) * 5
SCALES = (160, 80, 100, 160, 120)
RATE = 0.015
GAMMA = 0.99
STEP_LIMIT = 0.01
VALUE_SCALE = 600
FEATURE_CP = 100


def validate(weights):
    if len(weights) != len(NAMES) or any(
        type(w) not in (int, float) or not math.isfinite(w) or not 0.5 <= w <= 1.5
        for w in weights
    ):
        raise ValueError('Ungültige adaptive Gewichte.')
    return tuple(weights)


@dataclass(frozen=True)
class Position:
    material: int
    features: tuple[float, ...]

    def score(self, weights):
        return self.material + FEATURE_CP * sum(
            feature * weight for feature, weight in zip(self.features, weights)
        )

    def value(self, weights):
        return math.tanh(self.score(weights) / VALUE_SCALE)


def update(weights, before, after=None, reward=None):
    """Return new weights, prediction, target and TD error."""
    weights = validate(weights)
    prediction = before.value(weights)
    target = GAMMA * after.value(weights) if reward is None else reward
    if not math.isfinite(target) or abs(target) > 1:
        raise ValueError('Ungültiges Lernziel.')
    error = target - prediction
    gradient_scale = FEATURE_CP / VALUE_SCALE * (1 - prediction ** 2)
    result = []
    for weight, feature in zip(weights, before.features):
        if not math.isfinite(feature) or abs(feature) > 1:
            raise ValueError('Ungültiges Lernmerkmal.')
        step = RATE * error * gradient_scale * feature
        result.append(max(0.5, min(1.5, weight + max(-STEP_LIMIT, min(STEP_LIMIT, step)))))
    return validate(result), prediction, target, error
