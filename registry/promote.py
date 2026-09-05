"""Registry + promotion gate (06-TRACK-B-MODEL.md Phase 6, 10-EVALUATION.md).

Retrain when: a `critical` drift row fired, OR 4 weeks since the last retrain.

Promotion gate — ALL five must hold:
  1. challenger backtest MASE beats champion by >= 3% relative
  2. challenger does not lose by > 10% relative on ANY category
  3. coverage_80 within [0.72, 0.88]
  4. beat_seasonal_naive_pct_of_series not below the champion's
  5. identical folds, identical as_of discipline

Fail any → keep the champion, write why. A promotion log full of correct
rejections is better evidence than a log of constant promotions.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from drift import thresholds as T

DEFAULT_PATH = Path("data/registry/model_registry.json")


def load(path: Path = DEFAULT_PATH) -> dict:
    if not path.exists():
        return {"schema_version": 1, "models": [], "promotion_log": [],
                "champion": None, "updated_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


def save(reg: dict, path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def evaluate_promotion(
    challenger: dict, champion: dict | None, category_metrics: dict[str, float],
    champion_win_pct: float | None, challenger_win_pct: float | None,
) -> tuple[str, list[str]]:
    """The five-condition gate. Returns (decision, reasons).

    decision in {"promote", "keep"}; reasons are English sentences rendered on /model.
    """
    if champion is None:
        return "promote", ["First champion: no incumbent to beat."]

    reasons: list[str] = []
    cb = challenger["backtest"]
    chb = champion["backtest"]

    # 1. relative MASE improvement >= 3%
    champ_mase = chb.get("mase")
    chall_mase = cb.get("mase")
    rel = (champ_mase - chall_mase) / champ_mase if champ_mase else None
    if rel is None or rel < T.PROMOTE_MIN_RELATIVE_IMPROVEMENT:
        reasons.append(
            f"challenger MASE {chall_mase:.3f} vs champion {champ_mase:.3f} "
            f"({rel * 100:.1f}% better) is under the {T.PROMOTE_MIN_RELATIVE_IMPROVEMENT:.0%} gate."
            if rel is not None and rel >= 0 else
            f"challenger MASE {chall_mase:.3f} is worse than champion {champ_mase:.3f}."
        )

    # 2. no category regresses by > 10% relative
    for cat, mase in category_metrics.items():
        ch_cat = chb.get("categories", {}).get(cat)
        if ch_cat and ch_cat > 0:
            reg = (mase - ch_cat) / ch_cat
            if reg > T.PROMOTE_MAX_CATEGORY_REGRESSION:
                reasons.append(
                    f"{cat} regressed {reg:.0%} vs the champion's {ch_cat:.3f} "
                    f"(limit {T.PROMOTE_MAX_CATEGORY_REGRESSION:.0%})."
                )

    # 3. coverage in band
    cov = cb.get("coverage_80")
    if cov is None or not (T.PROMOTE_COVERAGE_LO <= cov <= T.PROMOTE_COVERAGE_HI):
        reasons.append(
            f"challenger coverage {cov if cov is not None else 'missing'} is outside "
            f"[{T.PROMOTE_COVERAGE_LO}, {T.PROMOTE_COVERAGE_HI}]."
        )

    # 4. win-rate not below champion's
    if champion_win_pct is not None and challenger_win_pct is not None:
        if challenger_win_pct < champion_win_pct:
            reasons.append(
                f"challenger win rate is {challenger_win_pct:.0%} (beats seasonal-naive "
                f"on that share of series) vs the champion's {champion_win_pct:.0%}."
            )

    # 5. same folds / as_of — enforced by construction in run_backtest; recorded
    if cb.get("folds") != chb.get("folds"):
        reasons.append(f"fold counts differ ({cb.get('folds')} vs {chb.get('folds')}).")

    return ("keep" if reasons else "promote"), reasons


def log_decision(reg: dict, decision: str, challenger_version: str, reason: str,
                 trigger: str, from_version: str | None) -> dict:
    reg.setdefault("promotion_log", []).append({
        "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "from": from_version,
        "to": challenger_version,
        "decision": decision,
        "reason": reason,
        "trigger": trigger,
    })
    return reg


def should_retrain(reg: dict, drift: list[dict], today: dt.date | None = None) -> tuple[bool, str]:
    """Drift fired at critical, OR 4 weeks since the last retrain (staleness floor)."""
    today = today or dt.date.today()
    if any(d.get("fired") and d.get("severity") == "critical" for d in drift):
        return True, "drift:critical"
    last = reg.get("models", [{}])[0].get("trained_at") if reg.get("models") else None
    if last:
        trained = dt.datetime.fromisoformat(last).date()
        if (today - trained).days >= 7 * T.RETRAIN_STALENESS_WEEKS:
            return True, f"staleness:{T.RETRAIN_STALENESS_WEEKS} weeks since {trained}"
    return False, "no trigger"
