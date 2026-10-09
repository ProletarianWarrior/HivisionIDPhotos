# HivisionIDPhotos 桌面版

把 HivisionIDPhotos 做成 Windows 双击即用的桌面工具：pywebview 原生窗口内嵌极简网页界面，
后端直接调用 `hivision` 核心推理（不依赖 Gradio），只内置 `hivision_modnet` 抠图模型（24.7MB）。

## 目录结构

- `server.py` — FastAPI 后端：`/api/presets`（尺寸/颜色预设）、`/api/idphoto`（生成证件照）、伺服 `static/`
- `main.py` — 桌面入口：起本地 uvicorn 服务，优先 pywebview 窗口，失败则自动打开系统浏览器
- `static/index.html` — 极简界面（原生 HTML/JS，无构建步骤）
- `app.spec` — PyInstaller onedir 打包配置
- `app.ico` — 应用图标（由 assets/hivision_logo.png 生成）

## 功能

- 上传单人照片（点击或拖拽，≤20MB）
- 18 种预设尺寸（一寸/二寸/签证/考试等，来自 `demo/assets/size_list_CN.csv`）+ 自定义宽高
- 6 种预设底色（来自 `demo/assets/color_list_CN.csv`）+ 自定义颜色；纯色/上下渐变/中心渐变
- 输出：标准照、高清照、透明底抠图、六寸排版照（PNG 下载）
- 可选"仅换底"模式（跳过裁剪）
- 多人脸/无人脸照片会提示错误，不产出结果

## 环境搭建（Python 3.10）

```bash
py install 3.10          # 若机器上没有 3.10
py -V:3.10 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt pillow fastapi "uvicorn[standard]" python-multipart pywebview pyinstaller
.venv\Scripts\python -m pip install requests tqdm   # download_model.py 的依赖
curl -L -o hivision/creator/weights/birefnet-v1-lite.onnx ^
  https://github.com/ZhengPeng7/BiRefNet/releases/download/v1/BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx
```

> 注 1：仓库自带的 requirements.txt 缺少 `pillow` 和 `python-multipart`（代码有用到），需补装。
> 注 2：`scripts/download_model.py` 的 `--models birefnet-lite` 选项有 bug（键名不匹配会 KeyError），
> 故 birefnet 用上面的 curl 直链下载；`hivision/plugin/beauty/` 的 gradio 顶层 import 已改为
> `__main__` 内导入，库本体不再依赖 gradio。

## 开发运行

```bash
.venv\Scripts\python -m desktop.main
```

## 打包

```bash
.venv\Scripts\pyinstaller desktop\app.spec --noconfirm --workpath build\pyinstaller --distpath build\dist
```

产物：`build\dist\HivisionIDPhotos\HivisionIDPhotos.exe`（onedir，整个文件夹约 250MB，
拷走整个 `HivisionIDPhotos` 文件夹即可在无 Python 的机器上运行）。

## 打包要点（排坑记录）

- 模型按 `hivision/creator/human_matting.py` 内 `__file__/weights` 相对路径加载，
  spec 里 datas 必须打到 `hivision/creator/weights`（见 app.spec）
- `mtcnnruntime` 的权重随 pip 包分发，需 `collect_data_files("mtcnnruntime")`
- `hivision/plugin/beauty/lut/` 是模块级加载的 LUT 图片，漏打会在 import 时直接崩溃
- `console=False` 双击启动时 `sys.stdout/stderr` 为 `None`，uvicorn 默认日志配置调
  `sys.stdout.isatty()` 会崩（"Unable to configure formatter 'default'"），
  必须 `uvicorn.Config(..., log_config=None)`；注意从控制台重定向输出启动时复现不了此问题
- WebView2 默认静默取消所有网页下载（`<a download>` 点了没反应），已开
  `webview.settings["ALLOW_DOWNLOADS"]`；PNG 保存走 `main.py` 的 `DesktopApi.save_file`
  （pywebview js_api 原生"另存为"对话框），浏览器回退模式下仍是 `<a download>` 直下
- 界面库已绕开 gradio，excludes 里再排除以防体积膨胀

## 抠图边缘质量（锯齿优化，方案 B）

当前使用 **birefnet-v1-lite**（224MB，MIT 许可）做抠图：复杂/锐利背景下质量显著优于
MODNet 系，代价是 CPU 推理约 10s/张（首次多 ~2s 模型加载；服务端已设 `RUN_MODE=beast`
常驻会话，后续每张约 8s）。界面提示文案已同步。

选型过程（`scripts/test_models.py`，输出在 `test/model_out/`）：

| 模型 | 体积 | CPU 耗时 | 硬背景表现 |
|---|---|---|---|
| hivision_modnet（25MB） | 25MB | 0.3s | 头发成块、残影、黑晕 |
| modnet_photographic（25MB） | 25MB | 0.3s | 头顶残叶、右侧背景残块 |
| rmbg-1.4（176MB，**非商用许可**） | 176MB | 1.5s | 头发区 alpha 塌陷成半透明 |
| **birefnet-v1-lite（224MB）** | 224MB | ~10s | 头发实、无残影、边缘自然 ✓ |

历史教训：曾给 MODNet 输出加 RGB 引导的 guided filter 羽化——虚化背景上效果好，
但锐利背景（竹竿/支架贴头）会把背景强边缘渗漏进 alpha（残块、半透明斑），已移除。
birefnet 的 alpha 自带自然软边，不再需要任何后处理滤波。
