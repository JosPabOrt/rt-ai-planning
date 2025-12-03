# srcfrom qa/engine/utils_naming.py

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Tuple, Optional


# ============================================
# 1) Tipos y dataclass para el naming
# ============================================

class StructCategory(Enum):
    BODY = auto()
    COUCH = auto()
    PTV = auto()
    CTV = auto()
    OAR = auto()
    HELPER = auto()      # anillos, opti, rings, crop, etc.
    UNKNOWN = auto()


@dataclass
class NormalizedName:
    original: str                  # nombre tal cual viene en RTSTRUCT
    cleaned: str                   # normalizado (mayúsculas, sin sufijos raros)
    canonical: str                 # órgano/rol canónico (RECTUM, PROSTATE, PTV_78, etc.)
    category: StructCategory       # PTV, OAR, etc.
    site_hint: Optional[str] = None  # "PROSTATE", "PELVIS", etc. (placeholder para futuro)


# ============================================
# 2) Reglas de limpieza de nombre
# ============================================

# Sufijos típicos que queremos quitar al "limpiar" el nombre
_SUFFIX_PATTERNS = [
    r"_OPT$", r"_OPTI$", r"_OPTIM$", r"_OPTIMIZ(E|ED)?$",
    r"_RING\d*$", r"_RING$", r"_SHELL\d*$", r"_SHELL$",
    r"_NEW$", r"_OLD$", r"_COPY$", r"_VIEJO$", r"_NUEVO$",
    r"_ROI\d*$",
    r"^\d+_",      # prefijos numéricos (ej. 1_RECTUM)
    r"_\d+$",      # sufijos numéricos (RECTUM_1, RECTUM_2)
]

# Palabras que consideramos ruido
_NOISE_TOKENS = {
    "STRUCT", "ROI", "ROIS", "OBJ", "OBJECT", "MASK", "CONTOUR",
}


def _clean_raw_name(raw: str) -> str:
    """
    Normalización básica:
      - mayúsculas
      - reemplazar espacios/puntos/guiones por "_"
      - quitar dobles "__"
      - quitar sufijos tipo _OPT, _RING, _1, etc.
    """
    n = raw.strip().upper()

    # Sustituir caracteres separadores por "_"
    n = re.sub(r"[ \.\-]+", "_", n)

    # Quitar sufijos conocidos
    for pattern in _SUFFIX_PATTERNS:
        n = re.sub(pattern, "", n)

    # Colapsar múltiples "_"
    n = re.sub(r"_+", "_", n)

    # Quitar "_" al inicio y fin
    n = n.strip("_")

    return n


# ============================================
# 3) Diccionarios de sinónimos / mappings
# ============================================

# Ojo: estos son ejemplos iniciales; los puedes enriquecer según tus datasets

# Mapeamos raw/clean a un "canonical organ name"
_CANONICAL_OAR_MAP: Dict[str, str] = {
    # PROSTATA / PROSTATE
    "PROSTATE": "PROSTATE",
    "PROSTATA": "PROSTATE",
    "GLAND_PROSTATE": "PROSTATE",

    # VEJIGA / BLADDER
    "BLADDER": "BLADDER",
    "VEJIGA": "BLADDER",

    # RECTO / RECTUM
    "RECTUM": "RECTUM",
    "RECTO": "RECTUM",
    "RECTUM_WALL": "RECTUM_WALL",
    "WALL_RECTUM": "RECTUM_WALL",

    # INTESTINO / BOWEL
    "BOWEL": "BOWEL",
    "BOWEL_BAG": "BOWEL",
    "SMALL_BOWEL": "SMALL_BOWEL",
    "LARGE_BOWEL": "LARGE_BOWEL",
    "INTESTINO_DELGADO": "SMALL_BOWEL",
    "INTESTINO_GRUESO": "LARGE_BOWEL",

    # Fémur / cabeza de fémur
    "FEMHEADNECK_L": "FEMUR_HEAD_L",
    "FEMHEADNECK_R": "FEMUR_HEAD_R",
    "FEMUR_HEAD_L": "FEMUR_HEAD_L",
    "FEMUR_HEAD_R": "FEMUR_HEAD_R",

    # Bulbo peneano
    "PENILEBULB": "PENILE_BULB",
    "PENILE_BULB": "PENILE_BULB",
    "BULBO_PENEANO": "PENILE_BULB",
}


_BODY_KEYWORDS = {"BODY", "EXTERNAL", "EXTERNAL_BODY", "OUTLINE"}
_COUCH_KEYWORDS = {"COUCH", "COUCHSURFACE", "COUCHINTERIOR", "TABLE"}

# Palabras que suelen indicar estructuras helper (no clínicas puras)
_HELPER_KEYWORDS = {
    "RING", "SHELL", "ZPTV", "OPT", "OPTI", "MARGIN", "CROP", "BLOCK", "PTV_RING",
}


def _canonical_from_clean(clean: str) -> Tuple[str, StructCategory]:
    """
    Decide canonical name + categoría a partir del nombre 'cleaned'.
    """

    # BODY
    for key in _BODY_KEYWORDS:
        if key in clean:
            return "BODY", StructCategory.BODY

    # COUCH
    for key in _COUCH_KEYWORDS:
        if key in clean:
            return "COUCH", StructCategory.COUCH

    # PTV (con varios roles posibles, pero eso lo resolveremos después)
    if "PTV" in clean:
        return clean, StructCategory.PTV

    # CTV
    if "CTV" in clean:
        return clean, StructCategory.CTV

    # Helper rings / opti / zPTV
    for key in _HELPER_KEYWORDS:
        if key in clean:
            return clean, StructCategory.HELPER

    # OARs: intentamos mapear al diccionario de sinónimos
    if clean in _CANONICAL_OAR_MAP:
        return _CANONICAL_OAR_MAP[clean], StructCategory.OAR

    # Si no hay match exacto, intentamos match parcial
    for raw_key, canon in _CANONICAL_OAR_MAP.items():
        if raw_key in clean:
            return canon, StructCategory.OAR

    # Si nada de lo anterior aplica, UNKNOWN
    return clean, StructCategory.UNKNOWN


# ============================================
# 4) API pública del módulo
# ============================================

def normalize_structure_name(raw_name: str) -> NormalizedName:
    """
    Normaliza un nombre de estructura y devuelve un NormalizedName:
      - original
      - cleaned
      - canonical
      - categoría (PTV/OAR/etc.)
    """
    cleaned = _clean_raw_name(raw_name)

    # Filtrar tokens de ruido
    tokens = [t for t in cleaned.split("_") if t not in _NOISE_TOKENS]
    cleaned = "_".join(tokens) if tokens else cleaned

    canonical, cat = _canonical_from_clean(cleaned)

    # Placeholder: podríamos inferir site_hint según canonical (p.ej. PROSTATE → "PROSTATE")
    site_hint = None
    if canonical == "PROSTATE":
        site_hint = "PROSTATE"
    elif canonical in {"RECTUM", "RECTUM_WALL", "BLADDER", "PENILE_BULB"}:
        site_hint = "PROSTATE"  # pelvian/prostate-ish; luego lo refinamos

    return NormalizedName(
        original=raw_name,
        cleaned=cleaned,
        canonical=canonical,
        category=cat,
        site_hint=site_hint,
    )


def group_structures_by_canonical(struct_names: List[str]) -> Dict[str, List[NormalizedName]]:
    """
    Dado un listado de nombres de estructuras, devuelve un dict:
        { canonical_name: [NormalizedName, ...] }
    Esto permite detectar duplicados de un mismo órgano.
    """
    groups: Dict[str, List[NormalizedName]] = {}
    for name in struct_names:
        norm = normalize_structure_name(name)
        groups.setdefault(norm.canonical, []).append(norm)
    return groups


def choose_primary_structure(
    normalized_group: List[NormalizedName],
) -> NormalizedName:
    """
    Dado un grupo de estructuras que comparten canonical_name,
    decide cuál tomar como 'principal'.
    Estrategia:
      - Preferir las que NO sean HELPER (si tuvieran categoría distinta en el futuro).
      - Por ahora, como NormalizedName no lleva volumen, elegimos:
          1) la que tenga cleaned más corto (menos sufijos raros),
          2) en empate, la primera alfabéticamente.
    Más adelante podemos pasar también el volumen y centroid para elegir por tamaño.
    """
    if not normalized_group:
        raise ValueError("Grupo vacío en choose_primary_structure")

    # Si en el grupo hubiera distintas categorias (OAR vs HELPER), preferimos no-HELPER
    non_helper = [n for n in normalized_group if n.category != StructCategory.HELPER]
    candidates = non_helper if non_helper else normalized_group

    # Elegimos por longitud del cleaned, luego orden alfabético
    candidates_sorted = sorted(
        candidates,
        key=lambda n: (len(n.cleaned), n.cleaned),
    )

    return candidates_sorted[0]

"""
utils_naming.py
================

Este módulo se encarga de *normalizar* y *clasificar* los nombres de las
estructuras (ROIs) que vienen del RTSTRUCT. El objetivo es poder trabajar
con nombres canónicos y categorías lógicas (PTV, CTV, OAR, BODY, COUCH,
estructuras helper, etc.) aun cuando el médico use variantes de nombre,
sufijos raros o múltiples versiones de la misma estructura.

¿Qué hace actualmente?
----------------------

1) Normalización agresiva del nombre bruto (raw_name):

   - Convierte a MAYÚSCULAS.
   - Sustituye espacios, puntos y guiones por "_".
   - Elimina sufijos frecuentes como:
       *_OPT, *_OPTI, *_RING, *_SHELL, *_NEW, *_OLD, *_1, *_2, etc.
   - Colapsa múltiples "_" en uno solo y los recorta al inicio/fin.
   - Elimina "tokens ruido" como STRUCT, ROI, OBJECT, MASK, etc.

   Esto produce un nombre "cleaned" que es más estable para hacer matching.

2) Mapeo a un nombre canónico ("canonical") y a una categoría:

   - BODY / COUCH:
       * Si el nombre contiene palabras clave como BODY, EXTERNAL, COUCH,
         COUCHSURFACE, TABLE, etc. se clasifica como BODY o COUCH.

   - PTV / CTV:
       * Si el nombre contiene PTV → categoría PTV.
       * Si el nombre contiene CTV → categoría CTV.
       * En esta etapa el módulo NO decide aún si un PTV es boost,
         elective, etc.; solo sabe que es un PTV. Esa lógica vivirá en
         otro módulo (checks_structures / reglas por sitio).

   - Estructuras helper:
       * Si el nombre contiene RING, SHELL, ZPTV, OPTI, CROP, etc.,
         se marca como HELPER (aniIlos, volúmenes de optimización,
         shells, etc.).

   - OARs (órganos de riesgo):
       * Usa un diccionario de sinónimos (_CANONICAL_OAR_MAP) que mapea
         variantes ES/EN a un nombre canónico:
             PROSTATA → PROSTATE
             VEJIGA → BLADDER
             RECTO → RECTUM
             FEMHEADNECK_L → FEMUR_HEAD_L
             BOWEL_BAG → BOWEL
         y así sucesivamente.
       * Primero intenta un match exacto; si no, intenta match parcial
         (que el patrón esté contenido en el nombre limpio).

   - UNKNOWN:
       * Si nada de lo anterior aplica, la estructura se clasifica como
         UNKNOWN (puede ser algo muy específico o no mapeado aún).

3) Devuelve un objeto NormalizedName:

   NormalizedName(
       original = nombre tal cual está en el RTSTRUCT,
       cleaned  = nombre normalizado,
       canonical = nombre canónico (ej. RECTUM, PROSTATE, PTV_78_39),
       category  = StructCategory (BODY/PTV/OAR/HELPER/UNKNOWN),
       site_hint = pista de sitio anatómico (por ahora se usa solo
                   de forma básica, p.ej. PROSTATE → "PROSTATE")
   )

4) Agrupar y elegir la estructura "principal":

   - group_structures_by_canonical(struct_names):
       * Dado un listado de nombres originales (keys del dict de
         estructuras en Case), devuelve un dict:
             { canonical_name: [NormalizedName, ...] }
       * Esto permite detectar duplicados de un mismo órgano:
             RECTUM, Rectum_1, Rectum_OPTI, etc.

   - choose_primary_structure(normalized_group):
       * Dado un grupo de NormalizedName que comparten canonical_name,
         elige uno como "principal".
       * Estrategia actual:
           - Si hubiera mezcla de categorías (ej. OAR vs HELPER),
             se preferiría la NO-HELPER (por ahora casi todos los grupos
             de OAR vienen ya como OAR).
           - Se elige el que tenga el nombre "cleaned" más corto
             (menos sufijos raros) y, en caso de empate, el primero en
             orden alfabético.
         * Más adelante se puede mejorar este criterio usando el volumen
           de la estructura (p.ej. elegir el contorno más grande).

Limitaciones actuales
---------------------

- El diccionario de sinónimos (_CANONICAL_OAR_MAP) está orientado
  principalmente a pelvis / próstata (PROSTATE, RECTUM, BLADDER,
  BOWEL, FEMUR_HEAD, PENILE_BULB). No incluye todavía OARs de mama,
  pulmón, SNC, etc.

- La inferencia de site_hint es muy básica:
    PROSTATE → "PROSTATE"
    RECTUM/BLADDER/PENILE_BULB → "PROSTATE"
  y nada más. No hay lógica específica para otros sitios todavía.

- La clasificación PTV/CTV no separa aún boost vs elective vs nodal;
  simplemente marca cualquier nombre con "PTV" como categoría PTV. La
  lógica de roles (BOOST/HIGH/ELECTIVE) se implementará en otro módulo
  usando información de volumen, dosis, nombre, etc.

Cómo extender este módulo
-------------------------

1) Añadir más sinónimos de OARs o estructuras:

   - Editar el diccionario _CANONICAL_OAR_MAP en este archivo.
   - Añadir entradas del estilo:
       "PAROTID_L": "PAROTID_L",
       "PAROTIDA_IZQ": "PAROTID_L",
       "PAROTID_R": "PAROTID_R",
       "PAROTIDA_DER": "PAROTID_R",
   - Esto permite que variantes en español / inglés / abreviadas
     apunten al mismo canonical_name.

2) Añadir soporte para nuevos sitios anatómicos:

   - Ampliar _CANONICAL_OAR_MAP con órganos específicos del sitio:
       * Por ejemplo, para mama: HEART, LUNG_L, LUNG_R, BREAST_L, etc.
   - En la función normalize_structure_name(), ajustar la lógica de
     site_hint:
       * Si canonical == "BREAST_L" o "BREAST_R" → site_hint = "BREAST"
       * Si canonical in {"LUNG_L", "LUNG_R", "HEART"} → site_hint = "THORAX"
   - Esto permite que otros módulos (checks_dose, checks_plan, etc.)
     seleccionen el conjunto de reglas adecuado según el sitio.

3) Ajustar qué se considera BODY, COUCH o HELPER:

   - Modificar los sets:
       _BODY_KEYWORDS, _COUCH_KEYWORDS, _HELPER_KEYWORDS
   - Por ejemplo, si tu RTSTRUCT usa "EXTERNAL_CONTOUR" como body, puedes
     añadir "EXTERNAL_CONTOUR" a _BODY_KEYWORDS.
   - Si el servicio usa nombres distintos para shells de optimización,
     añadir esos patrones a _HELPER_KEYWORDS.

4) Cambiar el criterio para elegir estructura "principal" en un grupo:

   - La función choose_primary_structure() por ahora decide usando
     únicamente el nombre (cleaned). Si en el futuro quieres elegir
     por volumen:
       * Añadir como argumento adicional un dict {original_name: volume_cc}
         o directamente pasar las StructureInfo.
       * Cambiar el criterio de ordenación de candidates_sorted para
         preferir el mayor volumen, o el que esté más cerca de un
         volumen esperado.

5) Añadir lógica específica por sitio:

   - Aunque este módulo se enfoca en naming genérico, puedes usar
     site_hint como ancla para reglas específicas:
       * Por ejemplo, en un futuro podrías tener:
            if norm.site_hint == "BREAST":
                # aplicar ciertas normalizaciones/ajustes extra…
   - Sin embargo, para mantener la separación de responsabilidades,
     se recomienda poner las reglas clínicas (por sitio/técnica)
     en otros módulos (checks_structures, checks_plan, checks_dose)
     y usar aquí solo la parte de "string → canonical_name/categoría".

Resumen
-------

En resumen, este módulo:
  - Toma nombres caóticos de estructuras del RTSTRUCT.
  - Los limpia, agrupa y los mapea a nombres canónicos y categorías.
  - Proporciona utilidades para detectar duplicados y elegir una
    estructura "principal" por órgano.
  - Está listo para ser extendido con más sinónimos, más sitios
    anatómicos y criterios más sofisticados (p.ej. volumen), sin
    romper la API actual.
"""
