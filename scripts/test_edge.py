# -*- coding: utf-8 -*-
"""对比实验：抠图边缘质量优化。

A: hivision_modnet（默认，含 hollow_out_fix 阈值补丁）
B: A + guided filter alpha 羽化
C: modnet_photographic（demo 默认，无 hollow_out_fix）
D: C + guided filter alpha 羽化
输出整图 + 头发边缘放大条，便于对比锯齿。
"""
import os
import sys
import time

import cv2
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from hivision import IDCreator
from hivision.creator.choose_handler import choose_handler
from hivision.utils import add_background, hex_to_rgb

OUT = os.path.join(BASE, "test", "edge_out")
os.makedirs(OUT, exist_ok=True)


def guided_alpha(rgba: np.ndarray, radius: int = 6, eps: float = 1e-4) -> np.ndarray:
    """用自身 BGR 作引导的 guided filter 平滑 alpha，消除台阶锯齿。返回 RGBA(uint8)。"""
    bgr = rgba[:, :, :3].astype(np.float32) / 255.0
    a = rgba[:, :, 3].astype(np.float32) / 255.0
    k = (2 * radius + 1, 2 * radius + 1)

    mean_I = cv2.boxFilter(bgr, ddepth=-1, ksize=k)
    mean_a = cv2.boxFilter(a, ddepth=-1, ksize=k)
    corr_I = cv2.boxFilter(bgr * bgr, ddepth=-1, ksize=k)
    corr_Ia = cv2.boxFilter(bgr * a[:, :, None], ddepth=-1, ksize=k)
    var_I = corr_I - mean_I * mean_I
    cov_Ia = corr_Ia - mean_I * mean_a[:, :, None]

    coeff = cov_Ia / (var_I + eps)
    bias = mean_a - (coeff * mean_I).sum(axis=2)
    mean_c = cv2.boxFilter(coeff, ddepth=-1, ksize=k)
    mean_b = cv2.boxFilter(bias, ddepth=-1, ksize=k)

    q = (mean_c * bgr).sum(axis=2) + mean_b
    q = cv2.GaussianBlur(q, (0, 0), 0.6)  # 去掉残余 1px 台阶
    out = rgba.copy()
    out[:, :, 3] = np.clip(q * 255, 0, 255).astype(np.uint8)
    return out


def compose(rgba, hexcolor="638cce"):
    r, g, b = hex_to_rgb(hexcolor)
    bg = add_background(rgba, bgr=(b, g, r), mode="pure_color").astype(np.uint8)
    return bg


def edge_strip(img, y, x, h=160, w=360, zoom=3):
    """裁一条边缘区域并放大，方便观察锯齿。"""
    crop = img[y : y + h, x : x + w]
    return cv2.resize(crop, (w * zoom, h * zoom), interpolation=cv2.INTER_NEAREST)


CASES = {
    "A_modnet": ("hivision_modnet", False),
    "B_modnet_gf": ("hivision_modnet", True),
    "C_photo": ("modnet_photographic_portrait_matting", False),
    "D_photo_gf": ("modnet_photographic_portrait_matting", True),
}

IMAGES = {
    "casual": os.path.join(BASE, "test", "casual.jpg"),
    "studio": os.path.join(BASE, "test", "single.jpg"),
}

for img_name, img_path in IMAGES.items():
    img = cv2.imread(img_path)
    max_side = 1600
    scale = min(1.0, max_side / max(img.shape[:2]))
    if scale < 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    for case, (model, use_gf) in CASES.items():
        creator = IDCreator()
        choose_handler(creator, matting_model_option=model)
        t0 = time.time()
        result = creator(img, change_bg_only=True)
        elapsed = time.time() - t0

        rgba = result.matting
        if use_gf:
            rgba = guided_alpha(rgba)
        bg = compose(rgba)

        cv2.imwrite(os.path.join(OUT, f"{img_name}_{case}.png"), bg)
        print(f"{img_name} {case}: {elapsed:.2f}s (不含模型首载)")

        # 头发边缘放大条：取人脸框上方区域（用 alpha 质心粗略定位）
        alpha = rgba[:, :, 3]
        ys, xs = np.where(alpha > 128)
        if len(ys) > 0:
            top = ys.min() + 20
            cx = (xs.min() + xs.max()) // 2
            x0 = max(0, cx - 180)
            strip = edge_strip(bg, top, x0)
            cv2.imwrite(os.path.join(OUT, f"{img_name}_{case}_edge.png"), strip)

print("DONE ->", OUT)
