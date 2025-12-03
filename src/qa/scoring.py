# srcfrom qa/engine/scoring.py

from typing import List, Dict
from core.case import Case, CheckResult, QAResult


def aggregate_score(checks: List[CheckResult],
                    weights: Dict[str, float] | None = None) -> float:
    if weights is None:
        weights = {
            "CT geometry consistency": 1.0,
            "Mandatory structures present": 1.5,
            "PTV volume": 1.0,
            "PTV inside BODY": 1.5,
            "Isocenter vs PTV": 1.0,
            "Plan technique consistency": 1.0,
        }

    total_w = 0.0
    accum = 0.0
    for c in checks:
        w = weights.get(c.name, 1.0)
        total_w += w
        accum += c.score * w

    if total_w == 0.0:
        return 0.0

    return 100.0 * (accum / total_w)


def extract_recommendations(checks: List[CheckResult]) -> List[str]:
    recs: List[str] = []
    for c in checks:
        if not c.passed:
            recs.append(c.message)
    return recs


def build_qa_result(case: Case,
                    checks: List[CheckResult]) -> QAResult:
    total = aggregate_score(checks)
    recs = extract_recommendations(checks)
    return QAResult(
        case_id=case.case_id,
        total_score=total,
        checks=checks,
        recommendations=recs,
    )
