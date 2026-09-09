# Windows / Linux 相容性與打包收據

本次交付為原始碼 ZIP，包含目前 SQLite 資料。**需要已安裝 Python 3.9 以上及其標準函式庫 SQLite，不包含 Python 執行環境。** 不需 Node.js、npm、pip 套件或雲端服務。

## 修改檔案與原因

- `start.bat`：新增 Windows 入口。處理含空白的專案路徑、切換磁碟、Python 指令探索、版本與 SQLite 檢查、UTF-8、程式退出碼；失敗時暫停視窗供查看。檔案使用 ASCII 內容與 CRLF 換行。
- `start.sh`：保留 POSIX shell 入口，新增 Python 版本與 SQLite 檢查、UTF-8 與停用 bytecode。採 LF 換行，Linux 可直接 `sh start.sh`，不依賴 ZIP 解壓後的執行權限。
- `app.py`：SQLite 初始化、讀取、寫入交易完成後皆明確關閉連線，釋放 Windows 的資料檔案控制代碼。路徑持續使用 `pathlib`，預設資料位置以程式目錄為準。
- `tests/test_app.py`：測試連線也明確關閉，新增初始化後釋放檔案控制代碼的回歸測試。
- `tests/test_http.py`：新增 HTTP 讀寫結束後釋放連線的回歸測試。
- `README.md`：補上 Windows／Linux 解壓縮、啟動、停止、獨立資料庫與測試指令，移除啟動範例中的 macOS 專屬路徑。
- `.gitignore`：排除 ZIP 產物目錄 `dist/`。
- `COMPATIBILITY.md`、`RECEIPT.md`：補充本次相容性變更、證據與限制。

## 實際驗證

| 項目 | 指令或方法 | 實際結果 |
|---|---|---|
| 資料測試（非完整驗證） | `python3 -B -m unittest tests.test_app -v` | `Ran 22 tests in 0.139s` / `OK` |
| HTTP 測試（非完整驗證） | `python3 -X utf8 -B -m unittest tests.test_http -v` | `Ran 8 tests in 0.171s` / `OK` |
| macOS / Python 3.9.6 完整套件 | `python3 -X utf8 -B -m unittest discover -s tests -v` | **`Ran 42 tests in 0.325s` / `OK`** |
| Linux / Python 3.11.14 完整套件 | 在 Linux Docker 容器執行 `python -X utf8 -B -m unittest discover -s tests -v` | **`Ran 42 tests in 0.683s` / `OK`** |
| Linux 真實啟動 | 複製至 `車間 SHIFT with spaces`，從其他工作目錄呼叫 `sh start.sh --port 0 --db <中文空白路徑>` | HTTP 200、API 有 10 位初始人員、SIGINT 正常停止且 exit 0 |
| shell 語法與參數 | `sh -n start.sh`、`sh start.sh --help` | exit 0；顯示 `--port`、`--db` 選項 |
| JavaScript 語法 | `node --check static/app.js` | 無輸出，exit 0 |
| 啟動檔格式 | 位元組檢查 `.bat` 為 ASCII/CRLF、`.sh` 為 UTF-8/LF | PASS |
| Claude CLI 唯讀複查 | 讀取 Windows／Linux 啟動檔、資料庫程式與說明 | 未提出確定阻擋啟動的程式缺陷；已確認交易後關閉連線。不是 Windows 實機驗證 |
| ZIP 完整性 | CRC、逐檔 SHA-256、解壓與 SQLite `integrity_check` | PASS |

Linux 使用本機既有容器映像，測試過程不下載、不連網；原專案唯讀掛載，測試資料放在容器暫存目錄，結束移除容器。Docker 只是本次驗證工具，終端使用者不需要 Docker。

## 驗收條件

- **過**：Windows 啟動檔與使用說明已提供，Linux 啟動檔與說明已更新。
- **過**：macOS 與 Linux 各自完整 42 項測試通過，沒有跳過。
- **過**：Linux 實際啟動、非 ASCII／空白路徑、自訂 DB、本機 HTTP 與停止流程皆驗證。
- **沒跑到**：Windows 實機執行。沒有可用 Windows 或 Wine 環境；不能把程式審查及 Linux 通過宣稱為 Windows 實測。
- **沒跑到**：Windows 瀏覽器操作、Linux 桌面瀏覽器視覺驗證。API 測試不取代瀏覽器驗收。

## 壓縮檔內容

`dist/workshop-shift-windows-linux.zip` 解壓後只有一個 `workshop-shift/` 根目錄，內含完整應用程式、啟動檔、測試、說明與目前 `data/workshop.sqlite3`。SQLite 使用備份 API 建立一致快照，保留原資料；不複製執行中暫存 sidecar。排除 `.git`、`__pycache__`、`.pyc`、`.DS_Store` 與 ZIP 產物本身。

包內 `MANIFEST.json` 記錄每個交付檔案的大小與 SHA-256；包外另有 `.zip.sha256`。打包工具會檢查 ZIP CRC、每個檔案的 SHA-256、解壓縮及 SQLite `PRAGMA integrity_check`。

## 最可能被挑到的弱點

**Windows 尚無實機執行證據。** 已針對啟動指令、編碼、路徑與 SQLite 檔案釋放修正，但不同 Windows Python 安裝方式、終端機及防毒設定仍需要實機驗收。原排班產品限制（例如不限制跨週連續出勤）仍見 README。
