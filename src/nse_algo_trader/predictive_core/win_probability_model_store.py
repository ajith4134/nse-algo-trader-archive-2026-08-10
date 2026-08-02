"""Persistence for the trained win-probability model (Trunk IX PREDICTIVE-CORE; research/156).

The engine's CARRIED STATE — the fitted calibrated model + feature schema + evaluation metadata — is
serialised to disk with joblib and reloaded across restarts, so the loop serves a trained model without
retraining every process start. Atomic write (temp + rename) so a crash mid-save never corrupts the model.
"""

from __future__ import annotations

from pathlib import Path

import joblib

DEFAULT_WIN_MODEL_PATH = Path.home() / ".nse_algo_trader" / "win_probability_model.joblib"


def save_win_model(trained, path: Path = DEFAULT_WIN_MODEL_PATH) -> Path:
    """Atomically persist a `TrainedWinModel` (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(trained, tmp)
    tmp.replace(path)  # atomic on POSIX
    return path


def load_win_model(path: Path = DEFAULT_WIN_MODEL_PATH):
    """Load a persisted `TrainedWinModel`, or None when absent/unreadable (engine then trains fresh)."""
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None


def model_exists(path: Path = DEFAULT_WIN_MODEL_PATH) -> bool:
    return path.exists()
