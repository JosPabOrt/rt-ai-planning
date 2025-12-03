# src/dataset.py

import os
import numpy as np
import torch
from torch.utils.data import Dataset


class DoseDataset(Dataset):
    """
    Dataset para cargar archivos .npz procesados, con:
      - X: [C, Z, Y, X]
      - Y: [Z, Y, X]

    Por ahora carga volúmenes completos.
    Si tienes problemas de memoria, luego cambiamos a patches 3D.
    """

    def __init__(self, data_dir, patient_ids=None):
        """
        Parámetros:
          data_dir: carpeta con archivos .npz (ej. "../data_processed")
          patient_ids: lista de IDs (sin extensión) o None para usar todos
        """
        self.data_dir = data_dir

        if patient_ids is None:
            # Buscar todos los .npz
            all_files = [f for f in os.listdir(data_dir) if f.endswith(".npz")]
            self.patient_ids = [os.path.splitext(f)[0] for f in all_files]
        else:
            self.patient_ids = patient_ids

        self.patient_ids = sorted(self.patient_ids)

    def __len__(self):
        return len(self.patient_ids)

    def __getitem__(self, idx):
        pid = self.patient_ids[idx]
        npz_path = os.path.join(self.data_dir, pid + ".npz")

        data = np.load(npz_path, allow_pickle=True)
        X = data["X"]  # [C, Z, Y, X]
        Y = data["Y"]  # [Z, Y, X]

        # Convertir a tensores PyTorch
        X_t = torch.from_numpy(X).float()
        Y_t = torch.from_numpy(Y).float().unsqueeze(0)  # [1, Z, Y, X] como canal de salida

        return X_t, Y_t, pid
