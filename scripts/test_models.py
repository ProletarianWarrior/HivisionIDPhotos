# -*- coding: utf-8 -*-
"""方案B对比实验：三种抠图模型在硬背景照片上的质量与 CPU 耗时。

模型：
  photo      = modnet_photographic_portrait_matting（现役基线，25MB）
  rmbg       = rmbg-1.4（176MB）
  birefnet   = birefnet-v1-lite（224MB）
输出：整图合成 + 头顶边缘放大条，打印首载/纯推理耗时。
"""
import os
import sys
import time

import cv2

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from hivision import IDCreator
from hivision.creator.choose_handler import choose_handler
from hivision.utils import add_background, hex_to_rgb

OUT = os.path.join(BASE, "test", "model_out")
os.makedirs(OUT, exist_ok=True)

MODELS = {
    "photo": "modnet_photographic_portrait_matting",
    "rmbg": "rmbg-1.4",
    "birefnet": "birefnet-v1-lite",
}

IMAGES = {
    "bamboo": os.path.join(BASE, "test", "bamboo.jpg"),
    "casual": os.path.join(BASE, "test", "casual.jpg"),
}


def compose(rgba, hexcolor="638cce"):
    r, g, b = hex_to_rgb(hexcolor)
    return add_background(rgba, bgr=(b, g, r), mode="pure_color").astype(np.uint8)


import numpy as np  # noqa: E402

for img_name, img_path in IMAGES.items():
    img = cv2.imread(img_path)
    max_side = 1600
    scale = min(1.0, max_side / max(img.shape[:2]))
    if scale < 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    for case, model in MODELS.items():
        creator = IDCreator()
        choose_handler(creator, matting_model_option=model)

        t0 = time.time()
        result = creator(img, change_bg_only=True)
        first = time.time() - t0

        t0 = time.time()
        result = creator(img, change_bg_only=True)
        warm = time.time() - t0

        rgba = result.matting
        bg = compose(rgba)
        cv2.imwrite(os.path.join(OUT, img_name + "_" + case + ".png"), bg)

        # 头顶边缘放大条
        alpha = rgba[:, :, 3]
        ys, xs = np.where(alpha > 128)
        if len(ys) > 0:
            top = max(0, ys.min() + 10)
            cx = (xs.min() + xs.max()) // 2
            x0 = max(0, cx - 200)
            h = min(220, img.shape[0] - top)
            w = min(400, img.shape[1] - x0)
            crop = bg[top : top + h, x0 : x0 + w]
            crop = cv2.resize(crop, (w * 2, h * 2), interpolation=cv2.INTER_NEAREST)
            cv2.imwrite(os.path.join(OUT, img_name + "_" + case + "_edge.png"), crop)

        print(f"{img_name:8s} {case:9s} first={first:6.2f}s warm={warm:6.2f}s")

print("DONE ->", OUT)
