"""
NeuroNudge predictive engine.

We train a small Decision Tree Classifier on synthetic but realistically
distributed wellness data. The model outputs a "well-being risk" label
for the next 48 hours (0 = stable, 1 = at-risk) plus a probability.

We deliberately keep the model tiny and re-train on cold start so there
is no serialised artefact to ship — this keeps the serverless bundle small
and makes the logic fully auditable for the internship evaluation.

Given the risk label and the specific inputs, generate_nudges() returns
2-4 personalised, actionable recommendations.
"""

import numpy as np
from sklearn.tree import DecisionTreeClassifier

# ---------------------------------------------------------------------------
# 1. Build a synthetic training set
# ---------------------------------------------------------------------------
# Features: [sleep_hours, stress_level, screen_time_hours, activity_minutes]
# Label:    1 = predicted dip in well-being within 48h, 0 = stable
#
# The rule used to *label* the training data is a well-being heuristic drawn
# from public wellness research: chronic low sleep + high stress + heavy
# screen time + sedentary behaviour correlates with mood/anxiety dips.
def _generate_training_data(n_samples: int = 2000, seed: int = 42):
    rng = np.random.default_rng(seed)

    sleep       = rng.uniform(3.0, 10.0, n_samples)
    stress      = rng.integers(1, 11, n_samples)
    screen      = rng.uniform(0.5, 14.0, n_samples)
    activity    = rng.integers(0, 180, n_samples)

    # Composite risk score used only for labelling (not exposed at inference)
    risk_score = (
        (7.5 - sleep).clip(min=0) * 1.2      # sleep debt below 7.5h
        + (stress - 4).clip(min=0) * 0.8     # stress above 4
        + (screen - 6).clip(min=0) * 0.5     # screen time above 6h
        + (30 - activity).clip(min=0) * 0.03 # activity below 30 min
    )

    # Add mild noise so the tree cannot perfectly memorise
    risk_score = risk_score + rng.normal(0, 0.4, n_samples)

    labels = (risk_score > 3.0).astype(int)

    features = np.column_stack([sleep, stress, screen, activity])
    return features, labels


# ---------------------------------------------------------------------------
# 2. Train once per cold start
# ---------------------------------------------------------------------------
_X_train, _y_train = _generate_training_data()
_model = DecisionTreeClassifier(max_depth=6, min_samples_leaf=20, random_state=42)
_model.fit(_X_train, _y_train)


# ---------------------------------------------------------------------------
# 3. Public API
# ---------------------------------------------------------------------------
def predict(sleep_hours: float,
            stress_level: int,
            screen_time_hours: float,
            activity_minutes: int) -> dict:
    """
    Evaluate a single wellness entry.

    Returns:
        {
            "risk_label": 0 | 1,
            "risk_probability": float 0-1,
            "risk_level": "low" | "moderate" | "high",
            "nudges": [str, ...]
        }
    """
    x = np.array([[sleep_hours, stress_level, screen_time_hours, activity_minutes]])

    label = int(_model.predict(x)[0])
    # predict_proba returns [[p_class0, p_class1]]
    probability = float(_model.predict_proba(x)[0][1])

    if probability < 0.33:
        level = "low"
    elif probability < 0.66:
        level = "moderate"
    else:
        level = "high"

    nudges = generate_nudges(
        risk_level=level,
        sleep_hours=sleep_hours,
        stress_level=stress_level,
        screen_time_hours=screen_time_hours,
        activity_minutes=activity_minutes,
    )

    return {
        "risk_label": label,
        "risk_probability": round(probability, 3),
        "risk_level": level,
        "nudges": nudges,
    }


def generate_nudges(risk_level: str,
                    sleep_hours: float,
                    stress_level: int,
                    screen_time_hours: float,
                    activity_minutes: int) -> list[str]:
    """
    Turn model output + raw inputs into short, actionable recommendations.
    The rules are transparent so you can defend every suggestion in evaluation.
    """
    nudges: list[str] = []

    if sleep_hours < 6.5:
        nudges.append(
            "Aim for 7–8 hours of sleep tonight. Try dimming screens an hour before bed."
        )
    elif sleep_hours < 7.5:
        nudges.append("You're slightly under-rested — a 20-minute nap can restore focus.")

    if stress_level >= 7:
        nudges.append(
            "Stress is high. Try a 4-7-8 breathing cycle: inhale 4s, hold 7s, exhale 8s."
        )
    elif stress_level >= 5:
        nudges.append("Take a 5-minute mindfulness break between tasks today.")

    if screen_time_hours > 8:
        nudges.append(
            "Your screen time is heavy. Schedule a 30-minute offline window this evening."
        )
    elif screen_time_hours > 6:
        nudges.append("Follow the 20-20-20 rule: every 20 min, look 20 ft away for 20 sec.")

    if activity_minutes < 20:
        nudges.append("Try a 10-minute brisk walk — movement lifts mood within minutes.")
    elif activity_minutes < 45:
        nudges.append("Add a short stretch session; even 5 minutes helps circulation.")

    # Guarantee at least one positive message
    if not nudges:
        nudges.append("Great balance today — keep the routine that's working for you.")

    if risk_level == "high":
        nudges.insert(
            0,
            "Our model flags an elevated risk of a well-being dip in the next 48h. "
            "Be extra kind to yourself today."
        )

    return nudges[:4]
