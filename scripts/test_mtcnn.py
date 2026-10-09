# -*- coding: utf-8 -*-
"""调试 mtcnn 检测结果。"""
import os
import sys
import cv2

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from mtcnnruntime import MTCNN

mtcnn = MTCNN()
img = cv2.imread(os.path.join(BASE, "assets", "demoImage.jpg"))
print("shape:", img.shape)

small = cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2), interpolation=cv2.INTER_AREA)
faces, lm = mtcnn.detect(small, thresholds=[0.8, 0.8, 0.8])
print("scale2 thr0.8:", None if faces is None else len(faces))
if faces is not None:
    print(faces)

faces2, lm2 = mtcnn.detect(img)
print("full default thr:", None if faces2 is None else len(faces2))
if faces2 is not None:
    print(faces2)
