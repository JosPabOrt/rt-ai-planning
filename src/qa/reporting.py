# src/qa/engine/reporting.py

"""
reporting.py
============

Utilidades para imprimir un reporte legible del resultado
del Auto-QA (QAResult) en consola o en un notebook.

Controlado vía qa.config.get_reporting_config(), que soporta:
  - Perfiles de reporte (CLINICAL_QUICK, PHYSICS_DEEP, CUSTOM)
  - Filtros por grupo (CT, Structures, Plan, Dose, Other)
  - Filtros por estado (OK/WARN/FAIL)
  - Mostrar u ocultar detalles y recomendaciones
"""

from typing import Iterable, Dict, List, Tuple
from core.case import QAResult, CheckResult
from qa.config import get_reporting_config


# Config global (se refresca en cada print_qa_report)
_REPORT_CFG: Dict[str, object] = get_reporting_config()


# ------------------------------------------------------------
# Helpers de estilo y clasificación de estado
# ------------------------------------------------------------

def _color(text: str, status: str) -> str:
    """
    Aplica color según el status ("OK", "WARN", "FAIL") si use_colors=True.
    """
    if not _REPORT_CFG.get("use_colors", True):
        return text

    color_ok = _REPORT_CFG.get("color_ok", "\033[92m")
    color_warn = _REPORT_CFG.get("color_warn", "\033[93m")
    color_fail = _REPORT_CFG.get("color_fail", "\033[91m")
    color_reset = _REPORT_CFG.get("color_reset", "\033[0m")

    if status == "OK":
        c = color_ok
    elif status == "WARN":
        c = color_warn
    else:  # "FAIL" u otro
        c = color_fail

    return f"{c}{text}{color_reset}"


def _get_score_0_100(report: QAResult) -> float:
    """
    Intenta obtener un score global en escala 0–100 desde QAResult,
    probando distintos nombres de atributo y escalas.
    """
    candidate_attrs = ["global_score", "score", "overall_score", "total_score"]

    raw = None
    for attr in candidate_attrs:
        if hasattr(report, attr):
            raw = getattr(report, attr)
            break

    if raw is None:
        return 0.0

    try:
        raw = float(raw)
    except Exception:
        return 0.0

    # Heurística: si el valor está en [0, 1.5] asumimos que es 0–1 y lo pasamos a 0–100.
    if 0.0 <= raw <= 1.5:
        return raw * 100.0
    return raw


def _classify_status(chk: CheckResult) -> str:
    """
    Clasifica un CheckResult en "OK", "WARN" o "FAIL" usando:
      - chk.passed (bool)
      - chk.score (float)
      - thresholds de REPORTING_CONFIG["status_thresholds"]
    """
    thresholds = _REPORT_CFG.get("status_thresholds", {})
    ok_min = float(thresholds.get("ok_min", 0.9))
    warn_min = float(thresholds.get("warn_min", 0.4))

    # Si passed=False → FAIL directo
    if not chk.passed:
        return "FAIL"

    score = float(getattr(chk, "score", 0.0))

    if score >= ok_min:
        return "OK"
    elif score >= warn_min:
        return "WARN"
    else:
        # Score muy bajo pero chk.passed=True: lo tratamos como FAIL duro.
        return "FAIL"


# ------------------------------------------------------------
# Helpers para ordenar / agrupar checks
# ------------------------------------------------------------

def _iter_checks_grouped(
    checks_with_meta: Iterable[Tuple[CheckResult, str, str]]
):
    """
    Devuelve un iterador que produce tuplas de la forma:
      - ("GROUP_HEADER", group_name, None, None)
      - ("CHECK", group_name, chk, status)

    `checks_with_meta` es una lista de tuplas (chk, status, group_name).
    El comportamiento depende de REPORTING_CONFIG["group_checks_by"]:
      - "group": agrupa por group_name y ordena por nombre dentro.
      - "name": lista plana ordenada por nombre.
    """
    mode = _REPORT_CFG.get("group_checks_by", "name")

    if mode == "group":
        grouped: Dict[str, List[Tuple[CheckResult, str]]] = {}
        for chk, status, group_name in checks_with_meta:
            grouped.setdefault(group_name, []).append((chk, status))

        # Ordenar grupos por nombre
        for group_name in sorted(grouped.keys()):
            yield ("GROUP_HEADER", group_name, None, None)
            # Dentro del grupo, ordenar por nombre de check
            for chk, status in sorted(grouped[group_name], key=lambda t: t[0].name.lower()):
                yield ("CHECK", group_name, chk, status)
    else:
        # Modo plano → ignoramos grupos para el orden, solo ordenamos por nombre
        for chk, status, group_name in sorted(
            checks_with_meta, key=lambda t: t[0].name.lower()
        ):
            yield ("CHECK", group_name, chk, status)


# ------------------------------------------------------------
# Pretty printer principal
# ------------------------------------------------------------

def print_qa_report(report: QAResult) -> None:
    """
    Pretty printer principal para QAResult.

    Controlado por REPORTING_CONFIG + REPORTING_PROFILES:
      - REPORTING_ACTIVE_PROFILE = "CLINICAL_QUICK" / "PHYSICS_DEEP" / "CUSTOM"
      - include_groups: qué grupos (CT, Structures, Plan, Dose...) mostrar
      - include_statuses: qué estados (OK/WARN/FAIL) mostrar
      - show_details: mostrar detalles de cada check
      - show_recommendations_section: mostrar o no recomendaciones
    """
    global _REPORT_CFG
    _REPORT_CFG = get_reporting_config()  # refrescar perfil/ajustes

    cfg = _REPORT_CFG
    labels = cfg.get("labels", {})
    header_width = int(cfg.get("header_width", 70))
    bar_len = int(cfg.get("bar_length", 20))
    bar_char_full = cfg.get("bar_char_full", "#")
    bar_char_empty = cfg.get("bar_char_empty", "-")
    show_details = bool(cfg.get("show_details", True))

    # Filtros desde config
    include_groups_cfg = cfg.get("include_groups", None)
    # Normalizamos: None o [] → sin filtro, incluye todo
    if include_groups_cfg is None or len(include_groups_cfg) == 0:
        include_groups: List[str] | None = None
    else:
        include_groups = list(include_groups_cfg)

    include_statuses_cfg = cfg.get("include_statuses", ["OK", "WARN", "FAIL"])
    include_statuses = set(include_statuses_cfg)

    case_id = getattr(report, "case_id", "<unknown>")
    title = labels.get("title", "AUTO-QA REPORT")
    case_prefix = labels.get("case_prefix", "Caso")
    label_global_score = labels.get("global_score", "Score global")
    checks_section_label = labels.get("checks_section", "Detalles de checks")
    recs_section_label = labels.get("recommendations_section", "RECOMENDACIONES")
    no_recs_label = labels.get("no_recommendations", "No hay recomendaciones adicionales. ✓")
    end_label = labels.get("end", "FIN DEL REPORTE")

    # Encabezado
    print("\n" + "=" * header_width)
    print(f" {title}  —  {case_prefix}: {case_id}")
    print("=" * header_width)

    # Score global
    score = _get_score_0_100(report)
    score_clip = max(0.0, min(100.0, score))
    filled = int(score_clip / 100.0 * bar_len)
    bar = bar_char_full * filled + bar_char_empty * (bar_len - filled)

    print(f"\n{label_global_score}: {score:.1f} / 100")
    print(f"[{bar}]")

    # -------- Filtro de checks según config/perfil --------
    checks_meta: List[Tuple[CheckResult, str, str]] = []
    for chk in report.checks:
        group_name = getattr(chk, "group", None) or "Other"
        status = _classify_status(chk)

        # Filtro por grupo
        if include_groups is not None and group_name not in include_groups:
            continue

        # Filtro por status (OK/WARN/FAIL)
        if status not in include_statuses:
            continue

        checks_meta.append((chk, status, group_name))

    # Checks
    print(f"\n{checks_section_label}:")
    print("-" * header_width)

    for item_type, group_name, chk, status in _iter_checks_grouped(checks_meta):
        if item_type == "GROUP_HEADER":
            # Encabezado de grupo (ej. [Plan], [Dose], etc.)
            print(f"\n[{group_name}]")
            continue

        # item_type == "CHECK"
        status_colored = _color(f"[{status}]", status)
        print(f"{status_colored} {chk.name}  (score={chk.score:.2f})")
        print(f"    {chk.message}")

        if show_details and chk.details:
            if isinstance(chk.details, dict):
                for k, v in chk.details.items():
                    print(f"       - {k}: {v}")
            else:
                print(f"       details: {chk.details}")
        print()

    # -------- Recomendaciones --------
    if cfg.get("show_recommendations_section", True):
        print("=" * header_width)
        print(f" {recs_section_label}")
        print("=" * header_width)

        recs = getattr(report, "recommendations", None)
        bullet = cfg.get("recommendation_bullet", " - ")

        if not recs:
            print(no_recs_label + "\n")
        else:
            for rec in recs:
                print(f"{bullet}{rec}")
            print()

    # Fin
    print("=" * header_width)
    print(f" {end_label} ")
    print("=" * header_width + "\n")
