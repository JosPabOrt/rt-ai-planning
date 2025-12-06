# src/common/build_case.py

from typing import Dict, List, Optional, Tuple
import numpy as np
import os


from core.case import Case, StructureInfo, PlanInfo, BeamInfo
from core.geometry import compute_centroid, compute_volume_cc
from core.dicom_io import (
    load_ct_series,
    load_rtstruct,
    load_rtplan,
    load_rtdose,
    resample_dose_to_ct,
)



def _extract_beams_from_rtplan(ds_plan) -> List[BeamInfo]:
    """
    Extrae información básica de cada beam/arco de un RTPLAN (pydicom Dataset)
    y la empaqueta en una lista de BeamInfo.

    Intenta ser robusto:
      - Si faltan algunos campos, pone None.
      - Detecta si es arco mirando:
          * BeamType == 'DYNAMIC'  (Varian VMAT típico)
          * ó si hay ControlPointSequence con gantry angles distintos.
    """
    beams: List[BeamInfo] = []

    if not hasattr(ds_plan, "BeamSequence"):
        return beams

    for beam_ds in ds_plan.BeamSequence:
        beam_number = int(getattr(beam_ds, "BeamNumber", len(beams) + 1))
        beam_name = str(getattr(beam_ds, "BeamName", f"Beam_{beam_number}"))

        modality = getattr(beam_ds, "RadiationType", None)        # "PHOTON", "ELECTRON", etc.
        beam_type = getattr(beam_ds, "BeamType", None)            # "STATIC", "DYNAMIC", etc.

        # Angulos couch / colimador (a nivel de beam, si existen)
        couch_angle = None
        collimator_angle = None
        if hasattr(beam_ds, "ControlPointSequence") and len(beam_ds.ControlPointSequence) > 0:
            cp0 = beam_ds.ControlPointSequence[0]
            couch_angle = float(getattr(cp0, "PatientSupportAngle", 0.0))
            collimator_angle = float(getattr(cp0, "BeamLimitingDeviceAngle", 0.0))

        # Intento de determinar si es arco (gantry se mueve)
        gantry_start = None
        gantry_end = None
        is_arc = False

        if hasattr(beam_ds, "ControlPointSequence") and len(beam_ds.ControlPointSequence) >= 2:
            cp0 = beam_ds.ControlPointSequence[0]
            cp_last = beam_ds.ControlPointSequence[-1]

            g0 = float(getattr(cp0, "GantryAngle", 0.0))
            g1 = float(getattr(cp_last, "GantryAngle", 0.0))

            gantry_start = g0
            gantry_end = g1

            if abs(g1 - g0) > 1.0:
                is_arc = True

        # Otra pista: BeamType "DYNAMIC" suele indicar arco VMAT
        if beam_type is not None and "DYNAMIC" in str(beam_type).upper():
            is_arc = True

        beams.append(
            BeamInfo(
                beam_number=beam_number,
                beam_name=beam_name,
                modality=str(modality) if modality is not None else None,
                beam_type=str(beam_type) if beam_type is not None else None,
                is_arc=is_arc,
                gantry_start=gantry_start,
                gantry_end=gantry_end,
                couch_angle=couch_angle,
                collimator_angle=collimator_angle,
            )
        )

    return beams



from typing import Optional, List
from core.case import PlanInfo, BeamInfo

def _build_plan_info(ds) -> Optional[PlanInfo]:
    """
    Extrae información básica del RTPLAN (pydicom Dataset) para PlanInfo.
    Diseñado pensando en Eclipse/Halcyon, pero robusto.
    """
    if ds is None:
        return None

    # 1) Primer haz
    try:
        first_beam = ds.BeamSequence[0]
    except Exception:
        first_beam = None

    # 2) Energía nominal
    energy = "UNKNOWN"
    try:
        if first_beam is not None:
            cp0 = first_beam.ControlPointSequence[0]
            if hasattr(cp0, "NominalBeamEnergy"):
                energy = str(cp0.NominalBeamEnergy)
            elif hasattr(first_beam, "NominalBeamEnergy"):
                energy = str(first_beam.NominalBeamEnergy)
    except Exception:
        pass

    # 3) Técnica (heurística)
    technique = "UNKNOWN"
    try:
        if first_beam is not None:
            beam_type = getattr(first_beam, "BeamType", "").upper()  # STATIC / DYNAMIC
            has_gantry_rot = hasattr(
                first_beam.ControlPointSequence[0], "GantryRotationDirection"
            )
            if beam_type == "DYNAMIC" and has_gantry_rot:
                technique = "VMAT"
            elif beam_type == "STATIC":
                technique = "STATIC"
            else:
                technique = beam_type or "UNKNOWN"
    except Exception:
        pass

    # 4) Beams y num_arcs
    from core.case import BeamInfo  # import local para evitar ciclos

    beams = []
    num_arcs = 0
    try:
        seq = getattr(ds, "BeamSequence", [])
        for beam in seq:
            try:
                cps = getattr(beam, "ControlPointSequence", None)
                if cps is None or len(cps) == 0:
                    continue

                gantry_start = float(getattr(cps[0], "GantryAngle", 0.0))
                gantry_end   = float(getattr(cps[-1], "GantryAngle", 0.0))
                col_angle    = float(getattr(cps[0], "BeamLimitingDeviceAngle", 0.0))
                couch_angle  = float(getattr(cps[0], "PatientSupportAngle", 0.0))
                beam_type    = getattr(beam, "BeamType", "").upper()
                modality     = getattr(beam, "RadiationType", None)
                beam_number  = int(getattr(beam, "BeamNumber", 0))
                beam_name    = str(getattr(beam, "BeamName", f"Beam{beam_number}"))

                is_arc = False
                try:
                    rot_dir = getattr(cps[0], "GantryRotationDirection", "").upper()
                    if rot_dir in ["CW", "CCW"]:
                        is_arc = True
                except Exception:
                    pass

                beams.append(
                    BeamInfo(
                        beam_number=beam_number,
                        beam_name=beam_name,
                        modality=modality,
                        beam_type=beam_type,
                        is_arc=is_arc,
                        gantry_start=gantry_start,
                        gantry_end=gantry_end,
                        couch_angle=couch_angle,
                        collimator_angle=col_angle,
                    )
                )
            except Exception:
                continue

        # número de arcos: cuenta solo beams marcados como arco
        num_arcs = sum(1 for b in beams if b.is_arc)
    except Exception:
        pass

    # 5) Isocentro
    iso = (0.0, 0.0, 0.0)
    try:
        if first_beam is not None:
            iso_pos = first_beam.ControlPointSequence[0].IsocenterPosition  # [x,y,z] mm
            iso = (float(iso_pos[0]), float(iso_pos[1]), float(iso_pos[2]))
    except Exception:
        pass

    # 6) Prescripción (muy básica; se puede refinar luego)
    total_dose_gy = None
    num_fx = None
    dose_per_fx = None

    try:
        # Algunos RTPLAN usan DoseReferenceSequence, otros RTPrescriptionSequence, etc.
        if hasattr(ds, "DoseReferenceSequence"):
            drs = ds.DoseReferenceSequence[0]
            if hasattr(drs, "TargetPrescriptionDose"):
                total_dose_gy = float(drs.TargetPrescriptionDose)
        # Aquí podrías añadir más heurísticas según tu export de Eclipse
    except Exception:
        pass

    if total_dose_gy is not None and hasattr(ds, "FractionGroupSequence"):
        try:
            fg = ds.FractionGroupSequence[0]
            num_fx = int(getattr(fg, "NumberOfFractionsPlanned", 0))
            if num_fx > 0:
                dose_per_fx = total_dose_gy / num_fx
        except Exception:
            pass

    return PlanInfo(
        energy=energy,
        technique=technique,
        num_arcs=num_arcs,
        isocenter_mm=iso,
        beams=beams,
        total_dose_gy=total_dose_gy,
        num_fractions=num_fx,
        dose_per_fraction_gy=dose_per_fx,
    )


def _build_structures(
    masks: Dict[str, np.ndarray],
    spacing_zyx: Tuple[float, float, float],
    ct_origin_xyz: Tuple[float, float, float],
) -> Dict[str, StructureInfo]:
    """
    Convierte el dict de máscaras {nombre: mask[z,y,x]} en StructureInfo,
    calculando volumen en cc y centroide aproximado (en mm, coords de paciente).
    """
    dz, dy, dx = spacing_zyx          # (z,y,x) en mm
    ox, oy, oz = ct_origin_xyz        # (x,y,z) coords paciente
    voxel_vol_cc = (dx * dy * dz) / 1000.0  # mm^3 → cc

    structs: Dict[str, StructureInfo] = {}

    for name, mask in masks.items():
        mask_bool = mask.astype(bool)
        num_voxels = int(mask_bool.sum())
        volume_cc = num_voxels * voxel_vol_cc

        if num_voxels > 0:
            # indices [z,y,x]
            idx = np.argwhere(mask_bool)
            mean_z, mean_y, mean_x = idx.mean(axis=0)

            # convertir a coords de paciente (x,y,z)
            x_mm = ox + mean_x * dx
            y_mm = oy + mean_y * dy
            z_mm = oz + mean_z * dz
            centroid = (float(x_mm), float(y_mm), float(z_mm))
        else:
            centroid = (0.0, 0.0, 0.0)

        structs[name] = StructureInfo(
            name=name,
            mask=mask_bool,
            volume_cc=float(volume_cc),
            centroid_mm=centroid,
        )

    return structs




def build_case_from_dicom(
    patient_id: str,
    ct_folder: str,
    rtstruct_path: str,
    rtplan_path: Optional[str] = None,
    rtdose_path: Optional[str] = None,
) -> Case:
    """
    Construye un Case a partir de:
      - CT (folder con serie DICOM)
      - RTSTRUCT (ruta)
      - RTPLAN   (ruta opcional)
      - RTDOSE   (ruta opcional)

    Además de cargar CT y estructuras, si se proporciona RTDOSE:
      - Carga la dosis 3D.
      - La re-muestrea al grid del CT.
      - La guarda en metadata["dose_gy"] como np.ndarray [z,y,x] en Gy.
    """
    # 1) CT
    ct_image, ct_array, spacing_sitk, origin, direction = load_ct_series(ct_folder)
    sx, sy, sz = spacing_sitk               # SimpleITK: (sx, sy, sz)
    dz, dy, dx = sz, sy, sx                 # Nuestro convenio: (z,y,x)

    # 2) Estructuras
    masks = load_rtstruct(rtstruct_path, ct_folder)
    structs = _build_structures(
        masks=masks,
        spacing_zyx=(dz, dy, dx),
        ct_origin_xyz=origin,   # origin es (x,y,z)
    )

    # 3) Plan (opcional)
    plan_info: Optional[PlanInfo] = None
    if rtplan_path is not None and os.path.exists(rtplan_path):
        try:
            ds_plan = load_rtplan(rtplan_path)
            plan_info = _build_plan_info(ds_plan)
            print(f"[INFO] RTPLAN cargado: {rtplan_path} (Label={getattr(ds_plan, 'RTPlanLabel', 'N/A')})")
        except Exception as e:
            print(f"[WARN] Error al cargar RTPLAN {rtplan_path}: {e}")

    # 4) Metadata base
    metadata = {
        "ct_origin": origin,
        "ct_spacing_sitk": spacing_sitk,
        "ct_direction": direction,
        "ct_spacing_zyx": (dz, dy, dx),
        "ct_source_folder": ct_folder,
    }

    # 5) RTDOSE → dose_gy en grid del CT
    if rtdose_path is not None and os.path.exists(rtdose_path):
        try:
            dose_image, dose_array_raw, dose_spacing, dose_origin, dose_direction = load_rtdose(rtdose_path)
            dose_resampled_image, dose_resampled_array = resample_dose_to_ct(ct_image, dose_image)

            metadata["dose_gy"] = dose_resampled_array.astype(np.float32)
            metadata["dose_origin"] = dose_resampled_image.GetOrigin()
            metadata["dose_spacing_sitk"] = dose_resampled_image.GetSpacing()
            metadata["dose_direction"] = dose_resampled_image.GetDirection()
            metadata["dose_source_path"] = rtdose_path

            # Debug opcional
            print(f"[INFO] RTDOSE cargado y remuestreado: {rtdose_path}")
            print(f"       dose_gy shape={dose_resampled_array.shape}")
        except Exception as e:
            print(f"[WARN] Error al cargar/remuestrear RTDOSE {rtdose_path}: {e}")
            metadata["dose_load_error"] = f"{type(e).__name__}: {e}"

    else:
        if rtdose_path is not None:
            print(f"[WARN] RTDOSE no encontrado en ruta {rtdose_path}. Seguimos sin dosis.")

    # 6) Construir Case
    case = Case(
        case_id=patient_id,
        ct_hu=ct_array,
        ct_spacing=(dz, dy, dx),
        structs=structs,
        plan=plan_info,
        metadata=metadata,
    )

    return case