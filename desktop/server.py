# -*- coding: utf-8 -*-
"""
HivisionIDPhotos 桌面版后端：FastAPI 伺服极简网页界面并直接调用 hivision 核心推理。
仅使用 hivision_modnet 抠图模型 + mtcnn 人脸检测，不做任何出站网络请求。
"""
import base64
import csv
import os
import threading

# hivision 默认每次推理后释放模型会话；桌面工具常驻，设 beast 让 birefnet 会话留在
# 内存里，省去每次 ~2s 的重复加载（224MB 模型 CPU 推理本身约 10s）
os.environ.setdefault("RUN_MODE", "beast")

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from hivision import IDCreator
from hivision.creator.choose_handler import choose_handler
from hivision.creator.layout_calculator import (
    generate_layout_array,
    generate_layout_image,
)
from hivision.error import FaceError
from hivision.utils import add_background, hex_to_rgb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
STATIC_DIR = os.path.join(BASE_DIR, "static")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 上传图片上限 20MB

# 尺寸/颜色预设来源：仓库自带 CSV（打包时随 datas 带上）
SIZE_CSV = os.path.join(ROOT_DIR, "demo", "assets", "size_list_CN.csv")
COLOR_CSV = os.path.join(ROOT_DIR, "demo", "assets", "color_list_CN.csv")

creator = IDCreator()  # handler 在下方显式选择
choose_handler(creator, matting_model_option="birefnet-v1-lite")
# BiRefNet-lite：224MB，复杂背景抠图质量显著优于 MODNet 系（CPU 约 10s/张）。
# 其 alpha 自带自然软边，无需 guided filter（该滤波会把背景强边缘渗漏进 alpha），
# 也不做任何形态学补丁。
infer_lock = threading.Lock()  # onnxruntime 会话串行化，避免并发推理

app = FastAPI(title="HivisionIDPhotos Desktop", docs_url=None, redoc_url=None)


def _load_size_presets():
    presets = []
    if os.path.exists(SIZE_CSV):
        with open(SIZE_CSV, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                presets.append(
                    {"name": row["Name"], "height": int(row["Height"]), "width": int(row["Width"])}
                )
    return presets


def _load_color_presets():
    presets = []
    if os.path.exists(COLOR_CSV):
        with open(COLOR_CSV, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                presets.append({"name": row["Name"], "hex": row["Hex"].lstrip("#")})
    return presets


def _decode_to_bgr(data: bytes) -> np.ndarray:
    """上传字节 -> 3通道 BGR。核心库假定 BGR 输入。"""
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise HTTPException(status_code=400, detail="无法解析图片文件，请使用 JPG/PNG 格式")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img


def _png_b64(img: np.ndarray) -> str:
    """BGR 或 RGBA ndarray -> PNG base64。"""
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("PNG 编码失败")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _compose_bg(rgba: np.ndarray, color_hex: str, render: int) -> np.ndarray:
    """透明 RGBA 合成底色，返回 3 通道 BGR。render: 0纯色 1上下渐变 2中心渐变"""
    r, g, b = hex_to_rgb(color_hex)
    mode = ("pure_color", "updown_gradient", "center_gradient")[render]
    bg = add_background(rgba, bgr=(b, g, r), mode=mode).astype(np.uint8)
    return bg


@app.get("/api/presets")
def presets():
    return {"sizes": _load_size_presets(), "colors": _load_color_presets()}


@app.post("/api/idphoto")
def idphoto(
    file: UploadFile = File(...),
    height: int = Form(413),
    width: int = Form(295),
    color: str = Form("638cce"),
    render: int = Form(0),
    change_bg_only: bool = Form(False),
    layout: bool = Form(True),
):
    """
    生成证件照。返回 base64 PNG：
    - standard: 标准照（已合成底色）
    - hd: 高清真照片（已合成底色）
    - matting: 透明底抠图
    - layout: 六寸排版照（可选）
    """
    color = color.lstrip("#")
    if len(color) != 6:
        raise HTTPException(status_code=400, detail="背景色格式应为 6 位 HEX")
    if not (100 <= height <= 2000 and 100 <= width <= 2000):
        raise HTTPException(status_code=400, detail="尺寸超出范围")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="图片超过 20MB 限制")
    img = _decode_to_bgr(data)

    with infer_lock:
        try:
            result = creator(img, size=(height, width), change_bg_only=change_bg_only)
        except FaceError as e:
            return JSONResponse(
                status_code=422,
                content={"error": f"检测到 {e.face_num} 张人脸，请上传单人脸照片"},
            )

    if change_bg_only:
        # 仅换底：standard/hd/matting 是同一张图，合成一次即可
        standard_bg = hd_bg = _compose_bg(result.matting, color, render)
        matting_rgba = result.matting
    else:
        standard_bg = _compose_bg(result.standard, color, render)
        hd_bg = _compose_bg(result.hd, color, render)
        matting_rgba = result.matting

    resp = {
        "standard": _png_b64(standard_bg),
        "hd": _png_b64(hd_bg),
        "matting": _png_b64(matting_rgba),
    }

    if layout:
        # 排版照：六寸相纸 (1795x1205) 排布
        typography_arr, typography_rotate = generate_layout_array(
            input_height=height, input_width=width
        )
        layout_img = generate_layout_image(
            standard_bg,
            typography_arr,
            typography_rotate,
            height=height,
            width=width,
        ).astype(np.uint8)
        resp["layout"] = _png_b64(layout_img)

    return resp


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
