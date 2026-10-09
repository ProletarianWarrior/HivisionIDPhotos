# -*- coding: utf-8 -*-
"""
桌面入口：启动本地 FastAPI 服务，优先用 pywebview 原生窗口呈现；
pywebview 不可用时回退为自动打开系统浏览器。

开发运行（项目根目录）：
    .venv/Scripts/python -m desktop.main
"""
import base64
import pathlib
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from desktop.server import app  # noqa: E402

try:
    import webview  # pywebview
except Exception:  # noqa: BLE001 - 无 pywebview 时回退浏览器
    webview = None


class DesktopApi:
    """暴露给前端 JS 的原生能力（window.pywebview.api.*）。"""

    def save_file(self, suggested_name: str, b64_data: str):
        """弹出系统"另存为"对话框，把 base64 PNG 写入用户选择的位置。

        返回保存的绝对路径；用户取消返回 None。
        """
        if webview is None or not webview.windows:
            return None
        target = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=suggested_name,
            file_types=("PNG 图片 (*.png)",),
        )
        if not target:
            return None
        target = target if isinstance(target, str) else target[0]
        # resolve() 规范化路径（消除 .. 等相对片段），后缀强制为 .png
        path = pathlib.Path(target).expanduser().resolve()
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")
        path.write_bytes(base64.b64decode(b64_data))
        return str(path)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    port = _free_port()
    url = f"http://127.0.0.1:{port}/"

    # console=False 打包后双击启动时 sys.stdout/stderr 为 None，
    # uvicorn 默认日志配置会调用 sys.stdout.isatty() 直接崩溃；
    # log_config=None 跳过其日志配置即可规避（print 对 None 是安全 no-op）
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", log_config=None
    )
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # 等 server 就绪
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        sys.exit(1)

    if webview is not None:
        # WebView2 默认静默取消所有下载（<a download> 无效），打开兜底开关；
        # 主保存路径是上面的 js_api 原生"另存为"对话框
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.create_window(
            "证件照制作工具",
            url,
            js_api=DesktopApi(),
            width=1200,
            height=860,
            min_size=(900, 640),
        )
        webview.start()
    else:
        print("pywebview 不可用，改为打开系统浏览器", file=sys.stderr)
        webbrowser.open(url)
        try:
            while t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
