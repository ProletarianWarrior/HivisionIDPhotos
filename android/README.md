# HivisionIDPhotos 安卓版（方案 3 移植）

把桌面版证件照工具移植为独立的安卓 APP：模型在手机本地推理，完全离线。

- 语言/界面：Kotlin + 原生 View（极简界面）
- 推理：onnxruntime-android，birefnet-v1-lite（224MB，随 APK 内置 assets）
- 仅 arm64-v8a（2019 年后的手机全部覆盖）
- 最低系统：Android 8.0（minSdk 26）

## 目录

```
android/
  app/src/main/java/com/hivision/idphotos/
    MattingEngine.kt    推理引擎（对应 hivision/creator/human_matting.py 的 birefnet 路径）
    MainActivity.kt     选图 → 生成（蓝底一寸）→ 保存相册
  app/src/main/assets/birefnet-v1-lite.onnx   224MB 模型
  local.properties    指向本机 Android SDK（E:\vuedemo\android-tools\sdk）
```

## 本机构建

```bash
# 工具链（已装好）：E:\vuedemo\android-tools\{jdk17, gradle-8.7, sdk}
cd android
JAVA_HOME=E:\vuedemo\android-tools\jdk17 \
  E:\vuedemo\android-tools\gradle-8.7\bin\gradle.bat assembleDebug --no-daemon
# 产物：app/build/outputs/apk/debug/app-debug.apk（约 240MB）
```

发给别人：直接把 APK 文件发过去，对方点开安装（允许"未知来源"）即可，
无需任何商店和权限手续。

## 与桌面版的移植对照

| 桌面版（Python） | 安卓版（Kotlin） | 状态 |
|---|---|---|
| `get_birefnet_portrait_matting`（1024 缩放/ImageNet 归一化/sigmoid/双线性放大） | `MattingEngine.matte()` | ✅ 阶段1 |
| `add_background`（纯色合成） | `Bitmap.compositeOver()` | ✅ 阶段1 |
| `resize_image_esp(2000)` 输入限尺寸 | `loadDownscaled(2000)` | ✅ 阶段1 |
| 保存（PNG） | MediaStore 存相册 Pictures/HivisionIDPhotos | ✅ 阶段1 |
| mtcnn/retinaface 人脸检测（单脸校验+角度） | 待移植（计划 retinaface ONNX） | ⬜ 阶段2 |
| `adjust_photo` 证件照裁剪定位（头高/头距比例） | 待移植（纯数学，逐像素对照验证） | ⬜ 阶段2 |
| `generate_layout_*` 六寸排版 | 待移植 | ⬜ 阶段2 |
| 尺寸/颜色预设 CSV | 待内置 assets | ⬜ 阶段2/3 |
| 性能调优（FP16/NNAPI/GPU） | 待真机实测后做 | ⬜ 阶段4 |

## 真机测试关注点（阶段1 包）

1. 首次启动：复制模型到应用目录 + 加载，最久约 1 分钟，之后每次启动直接可用
2. 生成速度：旗舰机目标 10s 内/张（对比桌面 CPU 约 8.5s）
3. 效果：与桌面版同一模型，抠图质量应一致；重点看边缘是否同样干净
4. 内存：224MB 模型 + 1024×1024 中间张量，旗舰机（8GB+）应无压力
