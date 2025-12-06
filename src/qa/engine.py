# src/qa/engine.py

from typing import List

from core.case import Case, CheckResult, QAResult
from .checks import run_all_checks
from .scoring import build_qa_result


def evaluate_case(case: Case) -> QAResult:
    """
    Interfaz de alto nivel del Auto-QA.

    Toma un Case y devuelve un QAResult con:
      - total_score
      - lista de CheckResult
      - recomendaciones agregadas
    """
    # 1) Correr todos los checks definidos en qa.checks
    checks_list: List[CheckResult] = run_all_checks(case)

    # 2) Construir QAResult a partir de esos checks
    qa_result: QAResult = build_qa_result(case, checks_list)

    return qa_result
