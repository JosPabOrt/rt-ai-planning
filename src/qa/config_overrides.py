"""
qa.config_overrides
-------------------

Capa muy ligera para manejar overrides de configuración
(procedentes de la UI) sin tocar los diccionarios base
definidos en qa.config.

Schema del JSON (qa_overrides.json):

{
  "sections": {
    "CT": {
      "enabled": true,
      "weight": 0.25,
      "...": "otros campos opcionales"
    },
    "Plan": { ... }
  },
  "checks": {
    "CT.CT_GEOMETRY": {
      "enabled": true,
      "weight": 1.0,
      "params": {
        "required_dim": 3,
        "min_slices": 40
      },
      "texts": {
        "ok_msg": "...",
        "warn_msg": "...",
        "fail_msg": "..."
      }
    },
    "Plan.FRACTIONS_REASONABLE": { ... }
  }
}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple
import json
import copy

# Ruta por defecto (mismo directorio que qa/config.py)
OVERRIDES_FILE = Path(__file__).resolve().parent / "qa_overrides.json"

DEFAULT_OVERRIDES: Dict[str, Any] = {
    "sections": {},
    "checks": {},
}


# ---------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------

def load_overrides(path: str | Path | None = None) -> Dict[str, Any]:
    """
    Lee el archivo de overrides (JSON) y devuelve un dict
    siempre con claves 'sections' y 'checks'.

    Si no existe o está roto, devuelve DEFAULT_OVERRIDES.
    """
    p = Path(path) if path is not None else OVERRIDES_FILE

    if not p.exists():
        return copy.deepcopy(DEFAULT_OVERRIDES)

    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return copy.deepcopy(DEFAULT_OVERRIDES)

    if not isinstance(data, dict):
        return copy.deepcopy(DEFAULT_OVERRIDES)

    data.setdefault("sections", {})
    data.setdefault("checks", {})
    return data


def save_overrides(overrides: Dict[str, Any], path: str | Path | None = None) -> None:
    """
    Guarda el dict de overrides en disco.

    La UI llamará a esto (indirectamente, vía un endpoint FastAPI)
    cuando el usuario pulse "Guardar configuración".
    """
    p = Path(path) if path is not None else OVERRIDES_FILE

    to_dump = {
        "sections": overrides.get("sections", {}),
        "checks": overrides.get("checks", {}),
    }

    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(to_dump, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------
# Aplicar overrides sobre dicts ya clonados
# ---------------------------------------------------------------------

def _split_check_id(check_id: str) -> Tuple[str, str] | None:
    """
    'CT.CT_GEOMETRY' → ('CT', 'CT_GEOMETRY')
    Devuelve None si el formato no es válido.
    """
    if "." not in check_id:
        return None
    section, key = check_id.split(".", 1)
    return section, key


def apply_overrides_to_configs(
    sections_cfg: Dict[str, Dict[str, Any]],
    checks_cfg: Dict[str, Dict[str, Dict[str, Any]]],
    overrides: Dict[str, Any],
) -> None:
    """
    Modifica IN PLACE los dicts sections_cfg y checks_cfg
    aplicando lo que venga en overrides.

    - sections_cfg: GLOBAL_SECTION_CONFIG clonado
    - checks_cfg:   GLOBAL_CHECK_CONFIG clonado
    """
    # ---- Secciones ----
    for sec_id, sec_override in overrides.get("sections", {}).items():
        if sec_id not in sections_cfg:
            continue
        base = sections_cfg[sec_id]
        for k, v in sec_override.items():
            base[k] = v

    # ---- Checks ----
    for check_id, ck_override in overrides.get("checks", {}).items():
        split = _split_check_id(check_id)
        if split is None:
            continue
        section, key = split
        section_checks = checks_cfg.get(section)
        if not section_checks or key not in section_checks:
            continue

        base_cfg = section_checks[key]
        # Permitimos:
        #  - enabled
        #  - weight
        #  - cualquier otro campo libre (params, texts, etc.)
        for attr, val in ck_override.items():
            base_cfg[attr] = val
