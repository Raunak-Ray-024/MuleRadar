"""Loads scam_model.joblib (trained in the notebook) and scores one message.
Keep this file and scam_model.joblib next to main.py. If you retrain and copy a new
joblib over the old one, the server picks it up on the next request (no restart)."""
import os
import numpy as np

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scam_model.joblib")
_NAMES = {0: "genuine", 1: "scam", 2: "promo"}
_bundle, _stamp = None, None


def _load():
    global _bundle, _stamp
    if not os.path.exists(_PATH):
        return None
    stamp = os.path.getmtime(_PATH)
    if _bundle is None or stamp != _stamp:
        import joblib
        _bundle, _stamp = joblib.load(_PATH), stamp
    return _bundle


def predict(text: str):
    """Returns {"label": "scam"|"promo"|"genuine", "scores": {...}} or None if no model file."""
    b = _load()
    if b is None:
        return None
    model, thr = b["model"], float(b["threshold"])
    p, full = model.predict_proba([text])[0], np.zeros(3)
    for i, c in enumerate(model.classes_):
        full[int(c)] = p[i]
    label = 1 if full[1] >= thr else (0 if full[0] >= full[2] else 2)
    return {"label": _NAMES[label], "scores": {_NAMES[i]: round(float(full[i]), 3) for i in range(3)}}