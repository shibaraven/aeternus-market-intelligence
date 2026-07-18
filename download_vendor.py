"""
執行此腳本下載所有前端依賴到 frontend/vendor/
用法：在 aeternus-market-intelligence 目錄下執行
  python download_vendor.py
"""
import urllib.request, os, sys

VENDOR_DIR = os.path.join(os.path.dirname(__file__), 'frontend', 'vendor')
os.makedirs(VENDOR_DIR, exist_ok=True)

LIBS = [
    ("lightweight-charts.standalone.production.js",
     "https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"),
    ("chart.umd.min.js",
     "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"),
    ("html2canvas.min.js",
     "https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"),
    ("Sortable.min.js",
     "https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"),
    ("jspdf.umd.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"),
]

print("=" * 50)
print("  下載前端依賴庫")
print("=" * 50)

all_ok = True
for filename, url in LIBS:
    dest = os.path.join(VENDOR_DIR, filename)
    print(f"  下載 {filename}...", end=" ", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        with open(dest, "wb") as f:
            f.write(data)
        print(f"✓ ({len(data)//1024} KB)")
    except Exception as e:
        print(f"✗ 失敗: {e}")
        all_ok = False

if all_ok:
    print("\n✅ 全部下載完成！重新啟動 Flask 即可。")
else:
    print("\n⚠ 部分下載失敗，請檢查網路連線後重試。")
