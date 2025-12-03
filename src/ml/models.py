# src/models.py

import torch
import torch.nn as nn
import torch.nn.functional as F


class DoubleConv(nn.Module):
    """
    Bloque: (Conv3D -> BN -> ReLU) x 2
    """

    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv3d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm3d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv3d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm3d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.net(x)


class Down(nn.Module):
    """
    Downscaling: MaxPool3d -> DoubleConv
    """

    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.pool = nn.MaxPool3d(2)
        self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x):
        x = self.pool(x)
        x = self.conv(x)
        return x


class Up(nn.Module):
    """
    Upscaling: Upsample (o ConvTranspose3d) + concatenación + DoubleConv
    """

    def __init__(self, in_channels, out_channels):
        super().__init__()

        # Usamos Upsample en lugar de ConvTranspose para simplificar
        self.up = nn.Upsample(scale_factor=2, mode='trilinear', align_corners=True)
        self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x1, x2):
        # x1 = características de la rama que sube
        # x2 = skip connection (rama que baja)
        x1 = self.up(x1)

        # Ajuste por si hay diferencia de tamaño por divisiones
        diffZ = x2.size(2) - x1.size(2)
        diffY = x2.size(3) - x1.size(3)
        diffX = x2.size(4) - x1.size(4)

        x1 = F.pad(x1, [diffX // 2, diffX - diffX // 2,
                        diffY // 2, diffY - diffY // 2,
                        diffZ // 2, diffZ - diffZ // 2])

        x = torch.cat([x2, x1], dim=1)
        x = self.conv(x)
        return x


class OutConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv = nn.Conv3d(in_channels, out_channels, kernel_size=1)

    def forward(self, x):
        return self.conv(x)


class UNet3D(nn.Module):
    """
    U-Net 3D básico para predicción de dosis:
      Input: [B, C_in, Z, Y, X]
      Output: [B, 1, Z, Y, X]
    """

    def __init__(self, n_channels, n_classes=1, base_filters=16):
        """
        Parámetros:
          n_channels: canales de entrada (CT + máscaras)
          n_classes: canales de salida (1 = dosis)
          base_filters: número de filtros base (se van duplicando)
        """
        super().__init__()

        self.inc = DoubleConv(n_channels, base_filters)
        self.down1 = Down(base_filters, base_filters * 2)
        self.down2 = Down(base_filters * 2, base_filters * 4)
        self.down3 = Down(base_filters * 4, base_filters * 8)

        self.up1 = Up(base_filters * 8 + base_filters * 4, base_filters * 4)
        self.up2 = Up(base_filters * 4 + base_filters * 2, base_filters * 2)
        self.up3 = Up(base_filters * 2 + base_filters, base_filters)

        self.outc = OutConv(base_filters, n_classes)

    def forward(self, x):
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)

        x = self.up1(x4, x3)
        x = self.up2(x, x2)
        x = self.up3(x, x1)
        logits = self.outc(x)
        return logits
