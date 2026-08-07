"""GT-eval metrics suite — accuracy, precision, recall, F1 (per-class + macro/weighted),
confusion matrix, per-category, and capability binaries.

Two complementary views over the SAME gt-eval snapshot:

  ROUTING (structural, deterministic, judge-free): did the agent take the right coarse ACTION?
    gt_action   — canonicalized from the GT `expected` (ask / answer / refuse).
    pred_action — derived from the snapshot (results count, tools, answer text).
    Reproducible across runs (no LLM in the loop). The "acc / F1 / đủ cả" deliverable.

  QUALITY (LLM-judge): did the agent's FULL answer satisfy the GT? Overall + per-category
    pass-rate from judge verdicts. Noisy — a single judge swings 38-67%; ensemble (both-pass)
    is the stable signal. Pass --judge once (single) or twice (qwen,deepseek → ensemble).

Plus CAPABILITY binaries (P/R/F1): clarify-when-required, result-presence-correct.

Usage (env ai_restaurant; no backend needed — reads saved JSON):
  python backend/scripts/compute_gt_metrics.py \\
      [--snapshot plans/reports/gt-eval-results.json] \\
      [--judge plans/reports/gt-quality-judge-tc07-qwen.json] \\
      [--judge plans/reports/gt-quality-judge-tc07-deepseek.json] \\
      [--tag tc07]
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT = ROOT / "plans" / "reports" / "gt-eval-results.json"
DEFAULT_OUT = ROOT / "plans" / "reports" / "gt-metrics.json"

# --- diacritics fold (inline so the script is stdlib-only / backend-free) ---
def _fold(s: str | None) -> str:
    """NFD + strip combining marks + đ→d + lowercase (matches core.text_norm.fold_diacritics)."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "d").lower()


# Refuse markers — the deterministic OOD / grounding-refuse / no-prior answers (folded). When the
# agent returned NO results AND the answer carries one, pred_action = refuse (not ask, not answer).
_REFUSE_MARKERS = (
    "chi ho tro am thuc", "khong muon bia", "ngoai pham vi", "khong thuc hien",
    "khong tao du lieu", "khong tuan theo", "chua co du lieu thuc te de",
)
# Delegate-field names that mean "the agent should DO something (return/explain), not ask/refuse".
_ANSWER_DELEGATES = {"search_agent", "explanation_agent", "preference_agent"}


def gt_action(expected: dict) -> str:
    """Canonical GT coarse action: ask / answer / refuse.

    ask    — should_ask_clarification OR a required slot is missing (location/price_unit/...).
    refuse — nothing delegated AND coordinator_intent != search (OOD / injection / jailbreak).
    answer — otherwise (a search/explanation/preference was delegated, or a refinement)."""
    if expected.get("should_ask_clarification") or expected.get("missing_slots"):
        return "ask"
    delegate = expected.get("delegate_to") or []
    if not delegate and expected.get("coordinator_intent") != "search":
        return "refuse"
    return "answer"


def pred_action(case: dict) -> str:
    """Predicted coarse action from the snapshot behavior.

    refuse — no results + a refuse marker in the answer (OOD / grounding / no-prior-refuse).
    ask    — no results + no refuse marker + the answer poses a question ('?').
    answer — results returned, OR an empty-result honest answer (no question, no refuse)."""
    if case.get("error"):
        return "answer"  # an errored case is a failed answer, not an ask/refuse
    results = case.get("results") or []
    if results:
        return "answer"
    ans = _fold(case.get("answer") or "")
    if any(m in ans for m in _REFUSE_MARKERS):
        return "refuse"
    if "?" in ans:
        return "ask"
    return "answer"


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def classification_report(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    """sklearn-style per-class P/R/F1/support + accuracy + macro/weighted averages."""
    n = len(y_true)
    per_class: dict[str, dict] = {}
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        sup = sum(1 for t in y_true if t == lab)
        p, r, f = _prf(tp, fp, fn)
        per_class[lab] = {"precision": p, "recall": r, "f1": f, "support": sup,
                          "tp": tp, "fp": fp, "fn": fn}
    accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / n if n else 0.0
    macro_f1 = sum(per_class[l]["f1"] for l in labels) / len(labels) if labels else 0.0
    weighted_f1 = (sum(per_class[l]["f1"] * per_class[l]["support"] for l in labels) / n) if n else 0.0
    # Confusion matrix [true][pred].
    cm = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(y_true, y_pred):
        cm[t][p] += 1
    return {"per_class": per_class, "accuracy": accuracy, "macro_f1": macro_f1,
            "weighted_f1": weighted_f1, "confusion_matrix": cm, "n": n}


def _binary(y_true: list[bool], y_pred: list[bool]) -> dict:
    """P/R/F1 for a boolean capability (positive = the thing we want to hold)."""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and not p)
    tn = sum(1 for t, p in zip(y_true, y_pred) if not t and not p)
    p, r, f = _prf(tp, fp, fn)
    return {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def _fmt_report(rep: dict, labels: list[str], title: str) -> str:
    """Render a classification_report-style text block."""
    lines = [title, "=" * 64,
             f"{'':>10}{'precision':>11}{'recall':>9}{'f1-score':>10}{'support':>9}"]
    for lab in labels:
        c = rep["per_class"][lab]
        lines.append(f"{lab:>10}{c['precision']:>11.2f}{c['recall']:>9.2f}"
                     f"{c['f1']:>10.2f}{c['support']:>9d}")
    lines.append("-" * 64)
    lines.append(f"{'accuracy':>10}{'':>11}{'':>9}{rep['accuracy']:>10.2f}{rep['n']:>9d}")
    lines.append(f"{'macro avg':>10}{'':>11}{'':>9}{rep['macro_f1']:>10.2f}{rep['n']:>9d}")
    lines.append(f"{'weighted avg':>10}{'':>11}{'':>9}{rep['weighted_f1']:>10.2f}{rep['n']:>9d}")
    # Confusion matrix rows=true, cols=pred.
    lines.append("\nConfusion matrix (rows=true, cols=pred):")
    lines.append("        " + "".join(f"{l[:6]:>8}" for l in labels))
    for t in labels:
        lines.append(f"{t[:6]:>8}" + "".join(f"{rep['confusion_matrix'][t][p]:>8}"
                                              for p in labels))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="GT-eval metrics suite (acc / P / R / F1 / ...).")
    ap.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    ap.add_argument("--judge", action="append", default=[], help="Judge verdict JSON (repeatable).")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--tag", default=None, help="Filename tag (e.g. tc07 → gt-metrics-tc07.json).")
    args = ap.parse_args()

    cases = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    cases = [c for c in cases if not c.get("error")]  # errored cases are excluded from quality too

    # --- ROUTING (structural) ---
    labels = ["ask", "answer", "refuse"]
    y_true = [gt_action(c.get("expected") or {}) for c in cases]
    y_pred = [pred_action(c) for c in cases]
    routing = classification_report(y_true, y_pred, labels)

    # --- CAPABILITY binaries ---
    # Clarify-when-required: among cases where GT wants an ask, did the agent ask?
    ask_t = [t == "ask" for t in y_true]
    ask_p = [p == "ask" for p in y_pred]
    clarify_cap = _binary(ask_t, ask_p)
    # Result-presence-correct: GT expects results (answer w/ a search delegation) ↔ agent returned >0.
    gt_expect_results = [
        bool((c.get("expected") or {}).get("delegate_to"))
        and "search_agent" in ((c.get("expected") or {}).get("delegate_to") or [])
        and not (c.get("expected") or {}).get("should_ask_clarification")
        for c in cases
    ]
    pred_has_results = [bool(c.get("results")) for c in cases]
    result_cap = _binary(gt_expect_results, pred_has_results)

    # --- per-category routing accuracy (+ optional quality pass-rate) ---
    judges = []
    for jp in args.judge:
        verdicts = {v["id"]: v.get("pass") for v in json.loads(Path(jp).read_text(encoding="utf-8"))["verdicts"]}
        # Short distinct label: last '-' segment of the stem (e.g. 'qwen' / 'deepseek').
        stem = Path(jp).stem
        label = stem.rsplit("-", 1)[-1] if "-" in stem else stem
        judges.append((label, verdicts))
    per_cat: dict[str, dict] = {}
    for c, t, p in zip(cases, y_true, y_pred):
        cat = c.get("category") or "unknown"
        d = per_cat.setdefault(cat, {"n": 0, "routing_correct": 0})
        d["n"] += 1
        d["routing_correct"] += int(t == p)
        for name, verdicts in judges:
            d.setdefault(name + "_pass", 0)
            d[name + "_pass"] += int(bool(verdicts.get(c["id"])))
    for cat, d in per_cat.items():
        d["routing_accuracy"] = d["routing_correct"] / d["n"] if d["n"] else 0.0
        for name, _ in judges:
            d[name + "_rate"] = d[name + "_pass"] / d["n"] if d["n"] else 0.0

    # --- QUALITY overall (judge) ---
    quality = {}
    for name, verdicts in judges:
        passes = [bool(verdicts.get(c["id"])) for c in cases]
        quality[name] = {"pass": sum(passes), "n": len(passes),
                         "rate": sum(passes) / len(passes) if passes else 0.0}
    if len(judges) >= 2:
        both = [all(bool(verdicts.get(c["id"])) for _, verdicts in judges) for c in cases]
        quality["ensemble_both_pass"] = {"pass": sum(both), "n": len(both),
                                         "rate": sum(both) / len(both) if both else 0.0}

    # --- render + save ---
    print(_fmt_report(routing, labels, "ROUTING ACTION (structural, judge-free)"))
    print("\nCAPABILITY BINARIES (positive = desired behavior)")
    print("=" * 64)
    print(f"  clarify-when-required   P={clarify_cap['precision']:.2f} R={clarify_cap['recall']:.2f}"
          f" F1={clarify_cap['f1']:.2f}  (tp={clarify_cap['tp']} fp={clarify_cap['fp']} fn={clarify_cap['fn']})")
    print(f"  result-presence-correct P={result_cap['precision']:.2f} R={result_cap['recall']:.2f}"
          f" F1={result_cap['f1']:.2f}  (tp={result_cap['tp']} fp={result_cap['fp']} fn={result_cap['fn']})")
    print("\nPER-CATEGORY")
    print("=" * 64)
    print(f"{'category':>28}{'n':>4}{'rout_acc':>9}" + "".join(f"{n[:10]:>12}" for n, _ in judges))
    for cat in sorted(per_cat):
        d = per_cat[cat]
        row = f"{cat[:28]:>28}{d['n']:>4}{d['routing_accuracy']:>9.2f}"
        for name, _ in judges:
            row += f"{d[name + '_rate']:>12.2f}"
        print(row)
    if quality:
        print("\nQUALITY (LLM-judge)")
        print("=" * 64)
        for name, q in quality.items():
            print(f"  {name:>22}: {q['pass']}/{q['n']} = {q['rate']:.1%}")

    out = Path(args.out)
    if args.tag:
        out = out.with_name(f"gt-metrics-{args.tag}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"routing": routing, "capabilities": {"clarify_when_required": clarify_cap,
               "result_presence": result_cap}, "per_category": per_cat, "quality": quality}
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
