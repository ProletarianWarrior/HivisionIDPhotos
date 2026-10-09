# -*- mode: python ; coding: utf-8 -*-
"""HivisionIDPhotos 桌面版打包配置（onedir，仅 hivision_modnet 模型）。

用法（项目根目录、venv 内执行）：
    pyinstaller desktop/app.spec --noconfirm
"""
from PyInstaller.utils.hooks import collect_data_files

import os

ROOT = os.path.dirname(SPECPATH)  # spec 位于 desktop/ 下，ROOT 为项目根
P = lambda *parts: os.path.join(ROOT, *parts)  # noqa: E731

datas = [
    # 抠图模型：hivision/creator/human_matting.py 按 __file__/weights 相对路径加载。
    # BiRefNet-lite：复杂背景质量最好（CPU 约 10s/张）；服务器端 RUN_MODE=beast 缓存会话
    (P("hivision", "creator", "weights", "birefnet-v1-lite.onnx"),
     "hivision/creator/weights"),
    # 网页界面
    (P("desktop", "static"), "desktop/static"),
    # 尺寸/颜色预设 CSV（server.py 按 <根>/demo/assets 读取）
    (P("demo", "assets", "size_list_CN.csv"), "demo/assets"),
    (P("demo", "assets", "color_list_CN.csv"), "demo/assets"),
    # 美颜 LUT 查找表（whitening.py 模块级加载）
    (P("hivision", "plugin", "beauty", "lut"), "hivision/plugin/beauty/lut"),
]
# mtcnn 人脸检测权重随 mtcnnruntime 包分发
datas += collect_data_files("mtcnnruntime")

a = Analysis(
    [P("desktop", "main.py")],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "gradio",          # 界面已绕开
        "matplotlib",
        "tkinter",
        "IPython",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HivisionIDPhotos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[P("desktop", "app.ico")],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HivisionIDPhotos",
)
