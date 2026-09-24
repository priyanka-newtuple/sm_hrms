from __future__ import annotations

import json
from pathlib import Path

import pytest

from calc.evaluator import CalcContext, evaluate_node, to_number

GOLDEN = json.loads((Path(__file__).parent.parent / "calc" / "calc_golden.json").read_text())


def _ctx(raw: dict) -> CalcContext:
    return CalcContext(
        field_values=raw.get("field_values", {}),
        table_rows=raw.get("table_rows", {}),
        row=raw.get("row"),
        cells=raw.get("cells"),
    )


@pytest.mark.parametrize("case", GOLDEN, ids=[c["name"] for c in GOLDEN])
def test_golden_parity(case: dict) -> None:
    result = evaluate_node(case["spec"], _ctx(case["ctx"]))
    expected = case["expected"]
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_to_number_rejects_bool() -> None:
    assert to_number(True) is None
    assert to_number(False) is None
