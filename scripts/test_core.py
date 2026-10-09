# -*- coding: utf-8 -*-
"""验证核心推理链路：抠图 -> 换底 -> 排版照。仅用 hivision_modnet + mtcnn。"""
import os
import sys
import time
import cv2
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from hivision import IDCreator
from hivision.creator.layout_calculator import generate_layout_array, generate_layout_image
from hivision.utils import add_background, hex_to_rgb

OUT = os.path.join(BASE, "test", "core_out")
os.makedirs(OUT, exist_ok=True)

img = cv2.imread(os.path.join(BASE, "assets", "demoImage.jpg"), cv2.IMREAD_UNCHANGED)
img = img[:, :606]  # demoImage.jpg 是 4 人合影，裁最左单人测试
if img.ndim == 2:
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
elif img.shape[2] == 4:
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
print("input:", img.shape)

creator = IDCreator()  # 默认 handler：extract_human(hivision_modnet) + mtcnn

t0 = time.time()
result = creator(img, size=(413, 295))
print("idphoto ok in %.2fs" % (time.time() - t0))
print("standard:", result.standard.shape, "hd:", result.hd.shape)

cv2.imwrite(os.path.join(OUT, "standard.png"), result.standard)
cv2.imwrite(os.path.join(OUT, "hd.png"), result.hd)
cv2.imwrite(os.path.join(OUT, "matting.png"), result.matting)

# 换底（红色）
bgr = hex_to_rgb("d74532")
bgr = (bgr[2], bgr[1], bgr[0])
bg = add_background(result.standard, bgr=bgr, mode="pure_color").astype(np.uint8)
cv2.imwrite(os.path.join(OUT, "red_bg.png"), cv2.cvtColor(bg, cv2.COLOR_RGBA2BGR))

# 排版照：换底结果是 3 通道 BGR，转 RGB 后喂排版函数
arr, rot = generate_layout_array(input_height=413, input_width=295)
layout = generate_layout_image(
    cv2.cvtColor(bg, cv2.COLOR_BGR2RGB), arr, rot, height=413, width=295
)
cv2.imwrite(os.path.join(OUT, "layout.png"), cv2.cvtColor(layout, cv2.COLOR_RGB2BGR))

print("ALL OK ->", OUT)
