"""ResNet18 双分支融合模型定义"""
import torch
import torch.nn as nn
from torchvision import models


class ResNet18DualFusion(nn.Module):
    """双分支 ResNet18：浅层特征(256d) + 深层特征(384d) → 拼接(640d) → MLP → logit"""

    def __init__(self, dropout=0.5):
        super().__init__()
        base = models.resnet18(weights=None)
        self.stem = nn.Sequential(base.conv1, base.bn1, base.relu, base.maxpool)
        self.layer1 = base.layer1
        self.layer2 = base.layer2
        self.layer3 = base.layer3
        self.layer4 = base.layer4
        self.gap = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Linear(640, 256), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(256, 64), nn.ReLU(), nn.Dropout(dropout * 0.5),
            nn.Linear(64, 1),
        )

    def forward(self, x):
        x = self.stem(x)
        x = self.layer1(x)
        x = self.layer2(x)
        s = self.gap(x).flatten(1)          # shallow: 256d
        x = self.layer3(x)
        x = self.layer4(x)
        d = self.gap(x).flatten(1)          # deep: 384d
        return self.classifier(torch.cat([s, d], 1)).squeeze(1)
