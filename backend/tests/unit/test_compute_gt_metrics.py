"""Unit tests for compute_gt_metrics — guards the metric definitions (P/R/F1 math + action
canonicalization) against silent miscalculation. The script lives in scripts/, not a package,
so it is imported by path."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "compute_gt_metrics.py"
_spec = importlib.util.spec_from_file_location("compute_gt_metrics", _SCRIPT)
cm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cm)


# --- _prf: the P/R/F1 arithmetic ---
def test_prf_perfect_half_zero():
    p, r, f = cm._prf(10, 0, 0)
    assert (p, r, f) == (1.0, 1.0, 1.0)          # perfect
    p, r, f = cm._prf(8, 2, 2)
    assert abs(p - 0.8) < 1e-9 and abs(r - 0.8) < 1e-9 and abs(f - 0.8) < 1e-9
    p, r, f = cm._prf(0, 5, 5)
    assert (p, r, f) == (0.0, 0.0, 0.0)          # all wrong
    assert cm._prf(0, 0, 0) == (0.0, 0.0, 0.0)   # no data → 0, not a crash


# --- gt_action: GT coarse-action canonicalization (ask / refuse / answer) ---
def test_gt_action_canonicalization():
    # ask — clarification requested OR a slot missing.
    assert cm.gt_action({"should_ask_clarification": True}) == "ask"
    assert cm.gt_action({"missing_slots": ["location"]}) == "ask"
    # refuse — nothing delegated AND not a search intent (OOD / injection / jailbreak).
    assert cm.gt_action({"delegate_to": [], "coordinator_intent": "unclear"}) == "refuse"
    # TC-21: SQL injection but intent=search + delegate → answer (sanitize + search, not refuse).
    assert cm.gt_action({"delegate_to": ["search_agent"], "coordinator_intent": "search"}) == "answer"
    # answer — a search/explanation/preference was delegated.
    assert cm.gt_action({"delegate_to": ["explanation_agent"], "coordinator_intent": "explanation"}) == "answer"
    assert cm.gt_action({"delegate_to": ["preference_agent"], "coordinator_intent": "profile_lookup"}) == "answer"


# --- pred_action: snapshot-behavior → coarse action (tools-presence signal) ---
def test_pred_action_from_snapshot():
    # results returned → answer.
    assert cm.pred_action({"results": [{"name": "Phở X"}], "tools": {"merchant_search": 1}, "answer": "đây"}) == "answer"
    # tools empty (guard short-circuit) + refuse marker → refuse (OOD).
    assert cm.pred_action({"results": [], "tools": {}, "answer": "Mình chỉ hỗ trợ ẩm thực."}) == "refuse"
    # tools empty + no refuse → ask (a clarify/no-prior/dietary guard fired).
    assert cm.pred_action({"results": [], "tools": {}, "answer": "Bạn kể thêm món nhé"}) == "ask"
    # tools ran + results empty + no refuse → answer (honest empty / preference / explanation).
    assert cm.pred_action({"results": [], "tools": {"merchant_search": 1}, "answer": "Chưa tìm thấy quán."}) == "answer"
    # tools ran + results empty + grounding-refuse marker → refuse.
    assert cm.pred_action({"results": [], "tools": {"merchant_search": 1}, "answer": "Chưa có dữ liệu thực tế để so sánh."}) == "refuse"
    # errored case → counted as a failed answer, not ask/refuse.
    assert cm.pred_action({"error": "timeout", "results": [], "tools": {}, "answer": ""}) == "answer"


# --- classification_report: accuracy, macro/weighted F1, confusion matrix ---
def test_classification_report_math():
    y_true = ["ask", "ask", "answer", "answer", "refuse"]
    y_pred = ["ask", "answer", "answer", "ask", "refuse"]   # 3/5 correct
    rep = cm.classification_report(y_true, y_pred, ["ask", "answer", "refuse"])
    assert abs(rep["accuracy"] - 0.6) < 1e-9
    # ask: tp=1, fp=1 (the answer→ask), fn=1 (ask→answer) → P=R=F1=0.5
    ask = rep["per_class"]["ask"]
    assert (ask["tp"], ask["fp"], ask["fn"]) == (1, 1, 1)
    assert abs(ask["f1"] - 0.5) < 1e-9
    # answer: tp=1, fp=1 (ask→answer), fn=1 (answer→ask) → F1=0.5 (symmetric to ask here).
    assert abs(rep["per_class"]["answer"]["f1"] - 0.5) < 1e-9
    # refuse perfect.
    assert rep["per_class"]["refuse"]["f1"] == 1.0
    # confusion matrix [true][pred].
    assert rep["confusion_matrix"]["ask"]["answer"] == 1
    assert rep["confusion_matrix"]["refuse"]["refuse"] == 1
    # macro = mean of per-class F1 = (0.5 + 0.5 + 1.0)/3.
    assert abs(rep["macro_f1"] - (0.5 + 0.5 + 1.0) / 3) < 1e-9
    # weighted = support-weighted F1 = (0.5*2 + 0.5*2 + 1.0*1)/5 = 0.6 (was unguarded → a broken
    # weighted formula silently returning macro would pass every other assertion here).
    assert abs(rep["weighted_f1"] - 0.6) < 1e-9


# --- _binary: capability P/R/F1 ---
def test_binary_capability():
    # truth = [T,T,F], pred = [T,F,T] → tp=1, fp=1, fn=1, tn=0.
    b = cm._binary([True, True, False], [True, False, True])
    assert (b["tp"], b["fp"], b["fn"], b["tn"]) == (1, 1, 1, 0)
    assert abs(b["precision"] - 0.5) < 1e-9 and abs(b["recall"] - 0.5) < 1e-9
