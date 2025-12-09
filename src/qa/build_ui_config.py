# src/qa/build_ui_config.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
import copy

try:
    # Uso normal dentro del paquete
    from qa import config as qa_config
    from qa.config_overrides import load_overrides, apply_overrides_to_configs
except ImportError:
    # Para pruebas locales tipo "python build_ui_config.py"
    import config as qa_config  # type: ignore
    from config_overrides import load_overrides, apply_overrides_to_configs  # type: ignore


def _deepcopy_sections_and_checks() -> Dict[str, Any]:
    """
    Clona GLOBAL_SECTION_CONFIG y GLOBAL_CHECK_CONFIG para poder
    aplicar overrides sin tocar los dicts originales.
    """
    sections = copy.deepcopy(getattr(qa_config, "GLOBAL_SECTION_CONFIG", {}))
    checks = copy.deepcopy(getattr(qa_config, "GLOBAL_CHECK_CONFIG", {}))
    return {"sections": sections, "checks": checks}


def _build_sections_meta(sections_cfg: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convierte el dict de secciones en una lista amigable para la UI.
    """
    items: List[Dict[str, Any]] = []
    for sec_id, cfg in sections_cfg.items():
        items.append(
            {
                "id": sec_id,
                "label": cfg.get("label", sec_id),
                "enabled": bool(cfg.get("enabled", True)),
                "weight": float(cfg.get("weight", 1.0)),
                "order": int(cfg.get("order", 999)),
            }
        )
    items.sort(key=lambda x: x["order"])
    return items


def _build_checks_meta(
    checks_cfg: Dict[str, Dict[str, Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """
    Convierte el dict de checks por sección en una lista amigable para la UI.
    """
    items: List[Dict[str, Any]] = []

    for section, checks in checks_cfg.items():
        for check_key, cfg in checks.items():
            cid = f"{section}.{check_key}"
            items.append(
                {
                    "id": cid,
                    "section": section,
                    "check_key": check_key,
                    "result_name": cfg.get("result_name", cid),
                    "label": cfg.get("result_name", cid),
                    "enabled": bool(cfg.get("enabled", True)),
                    "weight": float(cfg.get("weight", 1.0)),
                    # Aquí puedes añadir más campos si luego quieres editar params/texts
                }
            )

    # Orden simple: por sección, luego por id
    items.sort(key=lambda x: (x["section"], x["id"]))
    return items


def get_effective_configs() -> Dict[str, Any]:
    """
    Punto central para obtener la configuración EFECTIVA
    (base + overrides) de secciones y checks.

    Lo usaremos tanto en la UI de Settings como en el Panel.
    """
    base = _deepcopy_sections_and_checks()
    sections_cfg = base["sections"]
    checks_cfg = base["checks"]

    overrides = load_overrides()
    apply_overrides_to_configs(sections_cfg, checks_cfg, overrides)

    return {
        "sections": sections_cfg,
        "checks": checks_cfg,
        "overrides": overrides,
    }


def build_ui_config() -> Dict[str, Any]:
    """
    Devuelve una estructura pensada para la UI de Settings.
    No mete conceptos de clínica/sitio/máquina todavía para mantenerlo simple.
    """
    eff = get_effective_configs()
    sections_cfg = eff["sections"]
    checks_cfg = eff["checks"]

    sections_meta = _build_sections_meta(sections_cfg)
    checks_meta = _build_checks_meta(checks_cfg)

    return {
        "sections": sections_meta,
        "checks": checks_meta,
        "raw": eff,  # por si la UI quiere ver el dict crudo
    }
