# 交付收據

## 2026-09-09：可關閉／重開的教學提示

- 修改 `static/index.html`：加入固定可見的教學總開關、單則提示視窗與關閉按鈕。
- 修改 `static/app.js`：10 個操作情境的提示，點擊開啟、×／Esc／點擊外部關閉、全域關閉／重新開啟、localStorage 記憶與跨分頁同步；提示操作不送出資料變更。切換頁面後重新掛載提示。儲存偏好失敗時仍可在本頁開關。
- 修改 `static/style.css`：沿用既有綠色風格，新增提示按鈕及浮層、窄螢幕寬度限制與列印隱藏。
- 修改 `README.md` 與本收據：補充教學操作方式及驗證；重新產生 `dist/workshop-shift-windows-linux.zip` 與 SHA-256。
- 實際指令：`node --check static/app.js` 無輸出、exit 0；收尾 `python3 -X utf8 -B -m unittest discover -s tests -v` 輸出 `Ran 42 tests in 0.331s`、`OK`。42 項屬既有排班／資料／HTTP 測試，不是新增提示的自動化 UI 測試。
- Chrome 實際操作：開啟自動排班提示時只出現教學、沒有業務確認視窗；Esc 關閉成功；全部關閉後 0 個提示按鈕；重新整理仍關閉；重新開啟後班表頁 5 個提示入口恢復；請假頁 3 個、人員頁 2 個、設定頁 1 個入口可見；提示內「關閉所有」成功；Enter 開啟、× 關閉、點擊外部關閉皆成功。全程未提交排班、請假或人員變更。
- 驗收：教學提示／隨時關閉／重新開啟／重新整理保留偏好，皆過。Windows 實機、觸控實機、跨分頁同步與禁止 localStorage 的環境，沒跑到。
- 最可能的弱點：偏好以瀏覽器及網址為單位，不是員工帳號設定；換電腦或改用不同網址時會回到預設開啟。

## 原始交付紀錄

> Windows／Linux ZIP 交付已追加相容性修正及 2 項連線釋放回歸測試，最新完整套件為 **42 項**。原始建置收據如下；本次修改、各平台實際輸出與未驗證項目請見 [COMPATIBILITY.md](COMPATIBILITY.md)。

日期：2026-09-08。角色：Codex 實作者（workspace-write），Claude CLI 獨立審查及核心測試作者。沒有 commit、push、切換分支或建立 worktree。

## 1. 檔案與目的

| 檔案 | 目的 |
|---|---|
| `app.py` | 本機 HTTP 服務、SQLite schema 與交易、API 驗證、人員／請假／規則／班次管理、CSV 匯出與本機來源限制 |
| `scheduler.py` | 依職務分組的最小成本最大流；避開請假、限制每週出勤、平衡工作量、保留過去安排 |
| `static/index.html` | 繁體中文應用程式入口、導覽、操作確認視窗 |
| `static/style.css` | 桌面與窄螢幕版面、週班表、狀態色彩及列印樣式 |
| `static/app.js` | 四個功能畫面、API 串接、調班、請假、人員管理、規則設定及缺額顯示 |
| `tests/test_scheduler.py` | Claude CLI 撰寫的 12 個排班核心驗收測試 |
| `tests/test_app.py` | 21 個資料、交易、規則、歷史安排與日期邊界回歸測試 |
| `tests/test_http.py` | 7 個真實 HTTP 測試，涵蓋完整操作流程、CSV、錯誤輸入、來源限制與併發一致性 |
| `tests/__init__.py` | 測試套件入口 |
| `start.sh` | 不需安裝額外依賴的一鍵啟動入口 |
| `.gitignore` | 排除 SQLite 使用資料、暫存及編譯快取 |
| `README.md` | 啟動、排班規則、備份、測試方式及已知限制 |
| `data/workshop.sqlite3` | 本機實際資料，由首次啟動建立；最初只有 3／5／2 共 10 位編號人員，測試不使用此檔 |
| `RECEIPT.md` | 本交付收據 |

## 2. 實際執行結果

開發時分項執行，未將分項結果當成完整驗證：

| 指令 | 實際輸出摘要 | 驗證範圍 |
|---|---|---|
| `PYTHONPYCACHEPREFIX=/private/tmp/workshop-pycache python3 -m unittest tests.test_scheduler -v` | `Ran 12 tests in 0.008s` / `OK` | 非完整驗證：排班核心 |
| `PYTHONPYCACHEPREFIX=/private/tmp/workshop-pycache python3 -m unittest tests.test_app -v` | 初版 `Ran 19 tests in 0.123s` / `OK` | 非完整驗證：資料與規則 |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_app -v` | 最終新增案例後 `Ran 21 tests in 0.129s` / `OK` | 非完整驗證：日期邊界與保留班次補強 |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_http -v` | `Ran 7 tests in 0.169s` / `OK` | 非完整驗證：HTTP 整合 |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` | **`Ran 40 tests in 0.295s` / `OK`，exit 0** | **收尾完整自動化測試套件；無跳過測試** |
| `node --check static/app.js` | 無輸出，exit 0 | JavaScript 語法 |
| `sh -n start.sh` | 無輸出，exit 0 | 啟動腳本語法 |
| `PYTHONPYCACHEPREFIX=/private/tmp/workshop-pycache python3 -m py_compile app.py scheduler.py` | 無輸出，exit 0 | Python 編譯 |
| `./start.sh` | `車間排班已啟動：http://127.0.0.1:8765` | 本機服務啟動 |
| `curl -fsS -o /private/tmp/workshop-preview.html -w '%{http_code}\n' http://127.0.0.1:8765/` | `200` | 本機首頁 HTTP 可達 |

執行期間的限制與處理：

- Claude CLI 在沙箱內兩次回覆 `Not logged in · Please run /login`；依使用者要求以沙箱外 CLI 使用既有登入後成功。實際執行了初次唯讀審查、測試撰寫、修正後唯讀複查三項任務。未使用略過 Claude 權限的旗標。
- 本機 socket 起初被沙箱阻擋（`PermissionError: [Errno 1] Operation not permitted`），改用允許本機 socket 的執行環境後，服務與 HTTP 測試皆成功。
- Python 編譯快取預設指向不可寫的系統快取目錄；將本次編譯快取放到 `/private/tmp/workshop-pycache` 後成功。啟動腳本直接關閉 bytecode 寫入。
- Sites CLI 說明指令受 npm registry 的 `ENOTFOUND` 阻擋。最終依使用者明確要求的 local web + SQLite，交付零第三方執行依賴的本機實作，沒有部署雲端網站或新增雲端資料庫。

## 3. 驗收條件對照

| 條件 | 狀態 | 證據 |
|---|---|---|
| 櫃檯 3 人、技師 5 人、現場接待 2 人 | 過 | seed 精確數量及重啟冪等測試 |
| 週一至週日均有人服務 | 過 | 預設每日 2／3／1，共 42 人次，每日每職務逐項斷言 |
| 考慮人員請假 | 過 | 請假排除、跨週起訖包含、既有班次移除、取消後可重排 |
| 人力不足不能硬排 | 過 | 三位櫃檯同日請假，確實回報缺 2 人；接待全休亦保留缺額 |
| 每週上限、手動排班防衝突 | 過 | 第六班拒絕、請假日拒絕、重複新增冪等、凍結過去班次仍計入上限 |
| SQLite 本機持久化 | 過 | 斷開再連線仍保有班表；正式檔與測試臨時檔分離 |
| Local web | 過 | 本機服務持續運作、首頁 200，已以 Chrome 開啟交付網址 |
| Codex + Claude CLI 實際協作 | 過 | Claude 實際讀檔審查並建立 12 項核心測試；Codex 修正與實跑 |
| CSV 匯出 | 過 | 真實 HTTP 下載、10 位人員與 42 人次、繁中 BOM、請假內容與公式跳脫 |
| 瀏覽器逐項點擊、視覺與手機尺寸驗收 | **沒跑到** | 已開啟預覽；本次沒有執行瀏覽器操作測試或截圖驗證，不能以 API 全綠替代 |

## 4. 沒做到的事與原因

- 沒有雲端部署：依指定交付本機網站。
- 沒有多班制、半日假、核准流程、跨週連續出勤限制、技能替補、版本歷程：本版採每日固定需求的整日單班工作模式，介面與 README 已明示。
- 沒有真實姓名：使用者未提供；已建立可改名的職務編號人員。
- 沒有宣稱符合法規或完整工時計算：本版只有出勤天數及班段規則。
- 未做實機瀏覽器逐項操作、外觀或手機 viewport 驗收：完整 40 項測試是核心、資料與 HTTP 測試，不包含這些項目。

## 5. 最可能被挑到的弱點

**每週最多 5 天不等於跨週最多連續工作 5 天。** 目前不限制跨週連續出勤；規則也未版本化，歷史班表顯示會套用目前的班段與最低需求。這版適合本機單班排程，但若要當正式人事工時或歷史稽核系統，這兩項需先補強。

Claude 初次提出的「一位櫃檯請兩天假必然缺額」經 Codex 要求實證後撤回：剩餘五個可用日仍可滿足五天上限，已以全覆蓋的回歸測試固定正確行為。最終日期上限的跨週問題則採納修正，並新增可編輯、可存設定的端點案例。
