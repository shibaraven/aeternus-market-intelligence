import os
import sys
import time
import threading
import webbrowser


def is_frozen():
    return getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")


def project_root():
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def bundle_root():
    if is_frozen():
        return sys._MEIPASS
    return project_root()


def data_dir():
    d = os.environ.get("AETERNUS_DATA") or os.path.join(project_root(), "data")
    os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(d, "reports"), exist_ok=True)
    return d


def frontend_dir():
    return os.environ.get("AETERNUS_FRONTEND") or os.path.join(bundle_root(), "frontend")


# PyInstaller SSL certificate workaround. This is only needed for frozen EXE mode.
if is_frozen():
    try:
        import certifi
        import shutil
        import tempfile

        cert_src = certifi.where()
        cert_dst = os.path.join(tempfile.gettempdir(), "aeternus_market_intelligence_cacert.pem")
        if os.path.abspath(cert_src) != os.path.abspath(cert_dst):
            shutil.copy2(cert_src, cert_dst)
        os.environ["SSL_CERT_FILE"] = cert_dst
        os.environ["REQUESTS_CA_BUNDLE"] = cert_dst
        os.environ["CURL_CA_BUNDLE"] = cert_dst
        certifi.where = lambda: cert_dst
    except Exception as ex:
        print(f"[WARN] SSL certificate setup skipped: {ex}")


os.environ["AETERNUS_DATA"] = data_dir()
os.environ["AETERNUS_FRONTEND"] = frontend_dir()

backend_path = os.path.join(bundle_root(), "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import app as flask_app_module  # noqa: E402

# Keep the imported application aligned with the launcher's writable paths.
flask_app_module.DATA_DIR = data_dir()
if hasattr(flask_app_module, "DB_PATH"):
    flask_app_module.DB_PATH = os.path.join(data_dir(), "aeternus_market_intelligence.db")
flask_app_module.app.static_folder = frontend_dir()


def open_browser():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    print("=" * 60)
    print("  Aeternus Market Intelligence")
    print("  http://127.0.0.1:5000")
    print("  Close this window or press Ctrl+C to stop the server")
    print("=" * 60)
    threading.Thread(target=open_browser, daemon=True).start()
    flask_app_module.app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
