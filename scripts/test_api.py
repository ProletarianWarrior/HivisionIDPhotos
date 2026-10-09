# -*- coding: utf-8 -*-
"""用 httpx/requests 直接测 FastAPI 服务端点（不起窗口）。"""
import io
import os
import sys

import cv2
import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

img = cv2.imread(os.path.join(BASE, "assets", "demoImage.jpg"))[:, :606]
ok, buf = cv2.imencode(".jpg", img)

from fastapi.testclient import TestClient
from desktop.server import app

client = TestClient(app)

r = client.get("/api/presets")
print("presets:", r.status_code, len(r.json()["sizes"]), "sizes,", len(r.json()["colors"]), "colors")

r = client.post("/api/idphoto", data={
    "height": 413, "width": 295, "color": "638cce", "render": 0,
    "change_bg_only": "false", "layout": "true",
}, files={"file": ("t.jpg", buf.tobytes(), "image/jpeg")})
print("idphoto:", r.status_code, list(r.json().keys()) if r.status_code == 200 else r.json())

# 多人脸错误路径
img4 = cv2.imread(os.path.join(BASE, "assets", "demoImage.jpg"))
ok4, buf4 = cv2.imencode(".jpg", img4)
r = client.post("/api/idphoto", data={
    "height": 413, "width": 295, "color": "ffffff", "render": 0,
    "change_bg_only": "false", "layout": "false",
}, files={"file": ("t.jpg", buf4.tobytes(), "image/jpeg")})
print("multiface:", r.status_code, r.json())

# 仅换底
r = client.post("/api/idphoto", data={
    "height": 413, "width": 295, "color": "d74532", "render": 1,
    "change_bg_only": "true", "layout": "false",
}, files={"file": ("t.jpg", buf.tobytes(), "image/jpeg")})
print("chgonly:", r.status_code, list(r.json().keys()) if r.status_code == 200 else r.json())

# 静态页
r = client.get("/")
print("index:", r.status_code, "text/html" in r.headers["content-type"])
print("ALL OK")
