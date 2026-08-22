"""LPRNet: Lightweight License Plate Recognition Network.

Architecture based on the LPRNet paper (Zherzong Xu et al., 2018):
- Small CNN backbone (depthwise separable convolutions)
- Wide-and-Attn block for spatial feature extraction
- CTC (Connectionist Temporal Classification) loss for sequence labeling
- No recurrent layers → very fast inference

Input:  (B, 3, 48, 144)  — resized plate crop
Output: (B, T, C)        — per-timestep class probabilities (CTC decoded)
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class ConvBNReLU(nn.Module):
    """Conv2d + BatchNorm + ReLU in one block."""

    def __init__(self, in_ch: int, out_ch: int, kernel_size: int = 3, stride: int = 1, groups: int = 1):
        super().__init__()
        padding = kernel_size // 2
        self.conv = nn.Conv2d(in_ch, out_ch, kernel_size, stride, padding, groups=groups, bias=False)
        self.bn = nn.BatchNorm2d(out_ch)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.relu(self.bn(self.conv(x)))


class DepthwiseConv(nn.Module):
    """Depthwise separable convolution: depthwise + pointwise."""

    def __init__(self, in_ch: int, out_ch: int, kernel_size: int = 3):
        super().__init__()
        padding = kernel_size // 2
        self.depthwise = nn.Conv2d(in_ch, in_ch, kernel_size, 1, padding, groups=in_ch, bias=False)
        self.pointwise = nn.Conv2d(in_ch, out_ch, 1, 1, 0, bias=False)
        self.bn = nn.BatchNorm2d(out_ch)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.depthwise(x)
        x = self.pointwise(x)
        return self.relu(self.bn(x))


class SmallBasicBlock(nn.Module):
    """SBB: two depthwise convs + pointwise — captures local character patterns."""

    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.block = nn.Sequential(
            DepthwiseConv(in_ch, out_ch // 4, kernel_size=3),
            DepthwiseConv(out_ch // 4, out_ch // 4, kernel_size=3),
            ConvBNReLU(out_ch // 4, out_ch, kernel_size=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class LPRNet(nn.Module):
    """LPRNet model for license plate character recognition.

    Args:
        num_classes: Number of character classes (excluding CTC blank).
        input_h: Input image height (default 48).
        input_w: Input image width (default 144).
    """

    def __init__(self, num_classes: int, input_h: int = 48, input_w: int = 144):
        super().__init__()
        self.num_classes = num_classes
        self.input_h = input_h
        self.input_w = input_w

        # Backbone: progressively downsample spatial dimensions
        self.backbone = nn.Sequential(
            ConvBNReLU(3, 64, kernel_size=3, stride=1),       # (B, 64, H, W)
            nn.MaxPool2d(3, 2, padding=1),                      # (B, 64, H/2, W/2)
            SmallBasicBlock(64, 128),                           # (B, 128, H/2, W/2)
            nn.MaxPool2d(3, 2, padding=1),                      # (B, 128, H/4, W/4)
            SmallBasicBlock(128, 256),                          # (B, 256, H/4, W/4)
            nn.Dropout2d(0.2),
            SmallBasicBlock(256, 256),                          # (B, 256, H/4, W/4)
            nn.MaxPool2d((3, 1), (2, 1), padding=(1, 0)),      # (B, 256, H/8, W/4)
            DepthwiseConv(256, 128, kernel_size=3),             # (B, 128, H/8, W/4)
            ConvBNReLU(128, 128, kernel_size=1),                # (B, 128, H/8, W/4)
            nn.Dropout2d(0.2),
            ConvBNReLU(128, 128, kernel_size=3),                # (B, 128, H/8, W/4)
        )

        # Global context: average pool across height → (B, 128, 1, W/4)
        self.global_avg = nn.AdaptiveAvgPool2d((1, None))

        # Classification head: 1x1 conv to num_classes+1 (CTC blank)
        self.head = nn.Conv2d(128, num_classes + 1, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, 3, H, W) input plate image.

        Returns:
            logits: (B, T, C) where T = W/4 (timesteps), C = num_classes+1.
        """
        x = self.backbone(x)
        x = self.global_avg(x)        # (B, 128, 1, T)
        x = self.head(x)              # (B, C, 1, T)
        x = x.squeeze(2)              # (B, C, T)
        x = x.permute(0, 2, 1)        # (B, T, C) — for CTC loss
        return x

    @torch.no_grad()
    def predict(self, x: torch.Tensor) -> tuple[str, float]:
        """Greedy CTC decode: return (plate_text, confidence).

        Args:
            x: (B, 3, H, W) input image. B can be 1.

        Returns:
            (decoded_string, mean_confidence)
        """
        self.eval()
        logits = self.forward(x)            # (B, T, C)
        probs = F.softmax(logits, dim=-1)   # (B, T, C)
        pred = probs.argmax(dim=-1)         # (B, T)

        # CTC greedy decode: merge consecutive duplicates, remove blanks
        from training.config import IDX_TO_CHAR

        results = []
        confidences = []
        for b in range(pred.shape[0]):
            chars = []
            confs = []
            prev = -1
            for t in range(pred.shape[1]):
                idx = pred[b, t].item()
                conf = probs[b, t, idx].item()
                if idx != prev and idx < self.num_classes:
                    chars.append(IDX_TO_CHAR.get(idx, ""))
                    confs.append(conf)
                prev = idx
            results.append("".join(chars))
            confidences.append(sum(confs) / len(confs) if confs else 0.0)

        if len(results) == 1:
            return results[0], confidences[0]
        return results, confidences
