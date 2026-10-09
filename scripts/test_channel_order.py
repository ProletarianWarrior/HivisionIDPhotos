# -*- coding: utf-8 -*-
"""验证通道顺序假设：桌面版把 BGR 当 RGB 喂模型（PIL fromarray 怪癖），
安卓版喂的是标准 RGB。对比两者输出的背景区 alpha。"""
import os
import sys

import cv2
import numpy as np
import onnxruntime as ort

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sess = ort.InferenceSession(
    os.path.join(BASE, "hivision", "creator", "weights", "birefnet-v1-lite.onnx"),
    providers=["CPUExecutionProvider"],
)

img = cv2.imread(os.path.join(BASE, "test", "bamboo.jpg"))
h, w = img.shape[:2]
scale = 2000.0 / max(h, w)
if scale < 1:
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
ih, iw = img.shape[:2]


def infer(bgr):
    # 复刻桌面版：cv2 的 BGR 直接 fromarray 当 RGB 用
    from PIL import Image
    im = Image.fromarray(np.uint8(bgr)).resize((1024, 1024))
    a = np.asarray(im, dtype=np.float32) / 255.0
    a = (a - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    a = np.transpose(a, (2, 0, 1))[None].astype(np.float32)
    pred = sess.run(None, {"input_image": a})[-1]
    pred = np.squeeze(pred)
    return 1.0 / (1.0 + np.exp(-pred))


def corner_stats(alpha):
    box = 64
    vals = []
    for cy in (0, 1024 - box):
        for cx in (0, 1024 - box):
            vals.append(alpha[cy:cy + box, cx:cx + box].mean())
    center = alpha[462:562, 462:562].mean()
    return [f"{v * 100:.1f}%" for v in vals], f"{center * 100:.1f}%"


bgr_in = cv2.resize(img, (1024, 1024), interpolation=cv2.INTER_AREA)
rgb_in = bgr_in[:, :, ::-1].copy()

for label, arr in (("BGR(桌面怪癖)", bgr_in), ("RGB(安卓现状)", rgb_in)):
    alpha = infer(arr)
    corners, center = corner_stats(alpha)
    print(label, "四角alpha:", corners, "中心alpha:", center)
