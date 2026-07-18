# Aeternus Market Intelligence

Aeternus Market Intelligence 是一套以瀏覽器操作的多市場投資分析工作台，聚焦台灣、日本與上海市場。專案採用 Flask、原生 HTML/CSS/JavaScript 與 SQLite，預設在本機執行，不需要 Node.js 建置流程。

> 本專案提供的市場資料與分析結果僅供研究參考，不構成投資建議。

## 主要功能

- 多市場自選清單與 Yahoo Finance 報價
- 日線、盤中走勢與 SMA、EMA、MACD、RSI、布林通道等技術指標
- 技術訊號、策略回測、多週期共振與圖形辨識
- 股票比較、條件掃描、異常偵測、風險分析與市場熱力圖
- 交易日誌、投資組合配置、損益追蹤與分析
- 價格/指標警報與瀏覽器通知
- RSS 新聞彙整與規則式情緒分析
- 週報、PDF 與 Excel 匯出
- 選用本機 Ollama 模型產生 AI 分析，不會把對話送到雲端 AI API
- 繁體中文、簡體中文、日文與英文介面

## 系統架構

```text
Browser SPA (frontend/index.html)
        │ JSON / streaming
        ▼
Flask API (backend/app.py)
   ├── Yahoo Finance / RSS
   ├── SQLite (data/aeternus_market_intelligence.db)
   └── Ollama localhost:11434（選用）
```

`backend/main.py` 是原始碼與 PyInstaller 執行檔共用的啟動器；它會準備可寫入的資料目錄、啟動 Flask，並自動開啟瀏覽器。

## 快速啟動

需求：Python 3.12 或 3.13、pip。

Windows：

```bat
start.bat
```

macOS / Linux：

```bash
chmod +x start.sh
./start.sh
```

啟動腳本會建立專案內的 `.venv`、安裝依賴，然後開啟 [http://127.0.0.1:5000](http://127.0.0.1:5000)。

手動啟動：

```bash
python -m venv .venv
# Windows: .venv\Scripts\python -m pip install -r backend\requirements.txt
# macOS/Linux: .venv/bin/python -m pip install -r backend/requirements.txt
python backend/main.py
```

## 本機 AI（選用）

AI 功能會連線到本機的 Ollama `http://localhost:11434`，預設模型為 `llama3.2`。未安裝或未啟動 Ollama 時，其餘市場分析功能仍可正常使用。

## 資料與環境變數

應用程式會在首次啟動時自動建立 SQLite 資料庫與週報目錄。這些執行期資料已由 `.gitignore` 排除，不會提交到 Git。

| 變數 | 用途 | 預設值 |
| --- | --- | --- |
| `AETERNUS_DATA` | SQLite、週報與使用者資料目錄 | `<專案>/data` |
| `AETERNUS_FRONTEND` | 前端靜態檔案目錄 | `<專案>/frontend` |

## 建置 Windows 執行檔

```bat
build.bat
```

完成後的可攜式應用程式位於：

```text
dist/AeternusMarketIntelligence/
```

請移動整個資料夾，而不是只複製 `.exe`。

## 專案結構

```text
aeternus-market-intelligence/
├── backend/
│   ├── app.py                         # Flask API、分析邏輯與 SQLite
│   ├── main.py                        # 原始碼/封裝版啟動器
│   └── requirements.txt
├── frontend/
│   ├── index.html                     # 單頁前端
│   └── vendor/                        # 固定版本的前端依賴
├── data/                              # 執行期資料（Git 忽略）
├── AeternusMarketIntelligence.spec    # PyInstaller 設定
├── build.bat
├── download_vendor.py
├── start.bat
└── start.sh
```

## 主要 API

- `/api/quote`、`/api/history`、`/api/intraday`、`/api/fundamentals`
- `/api/analysis`、`/api/backtest`、`/api/resonance`、`/api/patterns`
- `/api/compare`、`/api/scan`、`/api/anomalies`、`/api/risk`、`/api/heatmap`
- `/api/journal`、`/api/portfolio/chart`、`/api/portfolio/analytics`
- `/api/alerts`、`/api/news`、`/api/report/*`、`/api/export/excel`
- `/api/ai/chat`、`/api/ai/models`

## Repository

[github.com/shibaraven/aeternus-market-intelligence](https://github.com/shibaraven/aeternus-market-intelligence)
