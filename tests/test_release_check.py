"""tools/release_check.py stays runnable and never reports an unmeasured gate as a pass."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import release_check as rc  # noqa: E402


def test_gates_run_on_the_real_gold_set():
    rows = rc.gates(os.path.join(ROOT, "gold"), os.path.join(ROOT, "predictions"))
    names = {name: status for status, name, _ in rows}
    assert names["Hallucinated INS numbers = 0"] == rc.PASS
    assert names["Allergen misses = 0"] == rc.PASS
    assert names["Every gold INS has an additives.json row"] == rc.PASS


def test_unmeasured_claim_gate_is_todo_not_pass(tmp_path):
    for d in ("gold", "pred"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "x.json").write_text(
            '{"ingredients": ["Wheat flour", "Salt"], "front_claims": ["Tasty"], '
            '"allergen_statement": null, "confidence": {"ingredients": 1.0}}')
    rows = rc.gates(str(tmp_path / "gold"), str(tmp_path / "pred"))
    status = next(s for s, n, _ in rows if n.startswith("False contradictions"))
    assert status == rc.TODO


def test_allergen_miss_is_caught(tmp_path):
    (tmp_path / "gold").mkdir(); (tmp_path / "pred").mkdir()
    (tmp_path / "gold" / "x.json").write_text(
        '{"ingredients": ["Wheat flour", "Milk solids"], "front_claims": [], "allergen_statement": null}')
    (tmp_path / "pred" / "x.json").write_text(       # the model dropped "Milk solids"
        '{"ingredients": ["Wheat flour"], "front_claims": [], "allergen_statement": null, '
        '"confidence": {"ingredients": 0.99}}')
    rows = rc.gates(str(tmp_path / "gold"), str(tmp_path / "pred"))
    status, _, detail = next(r for r in rows if r[1] == "Allergen misses = 0")
    assert status == rc.FAIL and "milk" in detail


def test_open_decisions_block_release():
    rows = rc.decision_gates()
    assert {n for _, n, _ in rows} == {f"{d} decided" for d in rc.DECISIONS_BEFORE_RELEASE}
