# ICCAD 2026 Problem A — 專案進度與待辦

> **專案**：LLM-Assisted Netlist Exploration and Transformation  
> **執行檔**：`./cada1089_alpha -config config.yaml`  
> **最後更新**：2026-06-18

---

## 一、專案目標（簡述）

建立兩層架構系統，參加 ICCAD 2026 Contest Problem A：

| 元件 | 說明 |
|------|------|
| **EDA 後端** | 解析 / 分析 / 變換 gate-level Verilog netlist |
| **AI Agent 前端** | 將自然語言請求對應到 EDA 操作，輸出符合規格的回應 |

**輸入**：flat Verilog（`and/or/nand/nor/not/buf/xor/xnor/dff`）、stdin 自然語言（逐行）  
**輸出**：stdout + `output/<case>/<case>.log`（`#RESPONSE <id>` … `#END <id>`）、`*_out.v`

---

## 二、目前已完成

### 2.1 四階段實作架構

| 階段 | 模組 | 狀態 |
|------|------|------|
| Step 1 | `parser.py` / `dag.py` / `writer.py` | ✅ Verilog 解析、DAG 內部表示、寫回 |
| Step 2 | `api.py` / `verify.py` / `transform.py` | ✅ 分析 API、變換 API、等價驗證與 rollback |
| Step 3 | `config.py` / `tool_spec.py` / `llm.py` / `handler.py` | ✅ YAML 設定、Tool Spec、OpenAI/Anthropic、規則優先路由 |
| Step 4 | `main.py` / `response.py` | ✅ stdin 迴圈、嚴格輸出格式、每 testcase 重置 response id |

### 2.2 已支援功能（摘要）

**基本**
- 初始化 testcase、載入 / 寫出設計

**分析**
- Gate 統計、fanin/fanout cone、路徑存在性、路徑列舉（含大電路保護）
- 邏輯深度、功能等價性、primary I/O 列表、gate 資訊等

**變換（含驗證後提交）**
- Fanout buffer 插入、移除 dangling、rename、inverter 合併
- 技術映射（AND/NOT、NAND/NOT）、XOR/XNOR 替換
- Cone depth 優化、duplicate 合併、常數傳播等

### 2.3 工程化

- 輸出統一目錄：`output/testNN/`（`.log` + `*_out.v`）
- 批次腳本：`scripts/run_all_tests.sh`、`scripts/run_tests_range.sh`
- `config.yaml` 已加入 `.gitignore`
- **LLM fallback 測試**：`CADCONTEST_FORCE_LLM=1` 跳過規則、全部走 LLM；
  `scripts/llm_fallback_eval.py` 以規則輸出為 golden 逐句對比 LLM（量化命中率）
- **工具目錄已對齊**：`tool_spec.py` 的 LLM 工具清單補齊 `extras.py` 全部工具，
  避免 LLM 因清單缺漏而選錯（例如「問幾個」誤選列舉工具）
- **LLM 健壯性**：`llm.py` 只解析第一個完整 JSON 物件（容忍模型多輸出）；
  `context.py` 加工具別名（`remap_xor_nand`→`replace_xor_nand` 等），避免 Unknown tool
- **case 名稱擷取**：`main.py`/`handler.py` 支援 `case name is "X"`（引號）與
  `beginning of testcase X` 兩種 PDF 句式（`extract_case_name`）
- **VM 部署**：`scripts/deploy_to_vm.sh`（經 EDAUnion 跳板 rsync + 可選 C++ 編譯）；
  用法見 `docs/DEPLOY.md`（三種模式：`upload` / `full` / `cpp`）

### 2.5 LLM fallback 全量評測（`CADCONTEST_FORCE_LLM`）

> 以規則輸出為 golden，強制全部走 LLM，量化 LLM 單獨命中率（2026-06-18）

- 全 40 題：**434/487 (89%) 命中**，mismatch=50，err=3（報告：`output/llm_fallback_report.txt`）
- 剩餘分歧主要類型：
  1. 工具選擇近似但不同（`fanout_report` vs `max_fanout_signal` vs `gates_driven_by`）
  2. gate 名（如 g0）當成 signal 餵給 `fanout_report` → 0，規則會先做 gate→output net 映射
  3. 「轉換後有幾個 X gate」規則答成「執行轉換」訊息，LLM 則回計數（部分情況 LLM 更正確）
  4. transform 後狀態相依，規則/LLM 順序差異導致數字不同（難以單純判定對錯）

### 2.6 PDF 規格合規檢查（A_20260212.pdf）

| 要求 | 狀態 | 備註 |
|------|------|------|
| 執行檔 `cadaXXXX_alpha -config <path>` | ✅ | `cada1089_alpha`（team 1089），`main.py` 解析 `-config` |
| 讀入單一 module flat Verilog | ✅ | `parser.py` 支援 module/port/wire（scalar+bus） |
| 原語 and/or/nand/nor/not/buf/xor/xnor + dff | ✅ | dff 實際格式 `.RN/.SN/.CK/.D/.Q` 已支援 |
| 常數 1'b0 / 1'b1 | ✅ | `Signal.parse` 處理 |
| bus（如 `[31:0]`） | ✅ | port/wire bus 解析 + 位元索引 |
| 寫出 gate-level Verilog | ✅ | `writer.py` |
| stdin 逐行請求 | ✅ | `main.py` 迴圈 |
| `#RESPONSE <id>`…`#END <id>`，id 由 1 遞增、每 testcase 重置 | ✅ | `response.py`；`#END` 同步輸出 stdout |
| 開頭句設定 case 名稱 / log 檔名（含引號、`testcase X` 句式） | ✅ | 已補強 `extract_case_name` |
| 寫 `<case>.log` | ✅ | `output/<case>/<case>.log` |
| LLM config（openai gpt-4o-mini / anthropic claude-haiku-4-5） | ✅ | `config.yaml` 與 PDF Figure 6 一致 |
| 向 LLM 描述 EDA 介面 | ✅ | `tool_spec.py` 注入 system prompt |
| 基本操作 ≤60s / 其他 ≤300s | ⚠️ | 多數遠低於上限；超大電路（test12 91k gates、test39）需留意 |

**潛在風險**：
- dff 若用小寫 `.q/.d` 實例，`parser.py` 的 `get("Q")/get("D")` 會漏接（目前 benchmark 為大寫，無問題）。
- 路徑完整枚舉在超大電路改為存在性回答，須確認評測是否接受。

### 2.4 Sample testcase 執行進度（40 題）

> 判定：**完整** = 回應數 = prompt 行數 且 有 `testNN_out.v`  
> 最近一次完整批次：2026-06-18，總耗時約 6.5 分鐘

| 狀態 | 數量 | Testcase |
|------|------|----------|
| ✅ 完整 | **40** | test01–test40 |
| ⚠️ 未完成 | **0** | — |

**最慢題目**：test39（105s）、test12（48s）、test35（48s）、test34（47s）、test37（31s）。

**test12 備註**：netlist 極大（約 **91,583 gates**），本次以 48s 完成 11/11；歷史上單次解析曾達 ~165 秒，視機器狀態而定。

---

## 三、40 題詳細狀態表

| Test | 回應數 | Prompt 行數 | 有 out.v | 狀態 |
|------|--------|-------------|----------|------|
| test01 | 3 | 3 | ✅ | 完整 |
| test02 | 4 | 4 | ✅ | 完整 |
| test03 | 4 | 4 | ✅ | 完整 |
| test04 | 4 | 4 | ✅ | 完整 |
| test05 | 4 | 4 | ✅ | 完整 |
| test06 | 5 | 5 | ✅ | 完整 |
| test07 | 6 | 6 | ✅ | 完整 |
| test08 | 7 | 7 | ✅ | 完整 |
| test09 | 8 | 8 | ✅ | 完整 |
| test10 | 9 | 9 | ✅ | 完整 |
| test11 | 10 | 10 | ✅ | 完整 |
| test12 | 11 | 11 | ✅ | 完整（超大電路，~48s） |
| test13 | 12 | 12 | ✅ | 完整 |
| test14 | 13 | 13 | ✅ | 完整 |
| test15 | 14 | 14 | ✅ | 完整 |
| test16 | 15 | 15 | ✅ | 完整 |
| test17 | 16 | 16 | ✅ | 完整 |
| test18 | 17 | 17 | ✅ | 完整 |
| test19 | 18 | 18 | ✅ | 完整 |
| test20 | 19 | 19 | ✅ | 完整 |
| test21 | 5 | 5 | ✅ | 完整 |
| test22 | 6 | 6 | ✅ | 完整 |
| test23 | 7 | 7 | ✅ | 完整 |
| test24 | 8 | 8 | ✅ | 完整 |
| test25 | 9 | 9 | ✅ | 完整 |
| test26 | 10 | 10 | ✅ | 完整 |
| test27 | 11 | 11 | ✅ | 完整 |
| test28 | 10 | 10 | ✅ | 完整 |
| test29 | 11 | 11 | ✅ | 完整 |
| test30 | 11 | 11 | ✅ | 完整 |
| test31 | 20 | 20 | ✅ | 完整 |
| test32 | 20 | 20 | ✅ | 完整 |
| test33 | 20 | 20 | ✅ | 完整 |
| test34 | 20 | 20 | ✅ | 完整 |
| test35 | 20 | 20 | ✅ | 完整 |
| test36 | 20 | 20 | ✅ | 完整 |
| test37 | 20 | 20 | ✅ | 完整 |
| test38 | 20 | 20 | ✅ | 完整 |
| test39 | 20 | 20 | ✅ | 完整（最慢，~105s） |
| test40 | 20 | 20 | ✅ | 完整 |

---

## 四、待解決問題

### 🔴 高優先

| # | 問題 | 影響 | 建議方向 |
|---|------|------|----------|
| 1 | **超大 netlist 效能**（test12：91k gates） | 大題耗時，極端情況可能逾時 | 優化 parser；或快取已解析 DAG；大電路分析走快速路徑 |
| 2 | **答案正確性未對標官方** | 有跑完 ≠ 有得分 | 需對照評測腳本 / golden answer（若公布）做 regression |

### 🟡 中優先

| # | 問題 | 影響 | 建議方向 |
|---|------|------|----------|
| 4 | 批次 **300s timeout** 對大題不夠 | test12/14/33 等曾 `exit 124` | 腳本已改 600s；大題可單獨跑、不設 timeout |
| 5 | **路徑完整枚舉** 在大電路上不可行 | Contest 若要求列舉所有 path 可能答錯 | 已對 >15k gates 改為「存在性 + 說明跳過枚舉」；需確認評測是否接受 |
| 6 | **規則匹配覆蓋率** | 未匹配時才呼叫 LLM（已移除 `CADCONTEST_NO_LLM`，批次也會走 LLM fallback）；LLM 工具清單已對齊 `extras.py` | 用 `scripts/llm_fallback_eval.py` 量化 LLM 命中率，持續補齊規則 / 強化 Tool Spec |
| 6b | **規則引擎既有 bug**（`llm_fallback_eval.py` 揪出） | test31 L12/L13 rename 類請求，新名稱被截斷 / 誤判成 rename_gate | 修正 `handler.py` 的 `rename_wire` / `rename_gate` 名稱擷取（`to\s+(\w+)` 與分支判斷） |
| 7 | **變換品質**（depth/fanout 優化） | 可能未達最優 cost | 加強 `optimize_cone_depth`、AIG/ABC 等（若允許） |

### 🟢 低優先 / 維護

| # | 問題 | 建議方向 |
|---|------|----------|
| 8 | `batch_status.csv` 可能過期 | 以 `output/testNN/` 實際檔案為準 |
| 9 | Verilog writer 與原始格式不完全一致 | 評測若只檢查功能可接受；否則改 writer 貼近 benchmark 風格 |
| 10 | API key 安全 | 勿 commit `config.yaml`；曾外洩需 rotate |

---

## 五、已知技術限制

1. **組合邏輯 DAG**：DFF Q 視為額外 PI，不處理時序等價。  
2. **功能等價**：窮舉 PI（≤18 bit），更大則隨機抽樣 512 組。  
3. **路徑枚舉**：上限 50 條 / 50k 步；超大電路改 BFS 存在性回答。  
4. **變換驗證**：與變換前 snapshot 比等價，非與「最初載入」比（除非呼叫 `verify_equivalence` 工具）。  

---

## 六、如何本地測試

```bash
cd cadcontest
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # 填入 api_key

# 單題（建議先 test01）
cat testcase/test01/prompt.txt | ./cada1089_alpha -config config.yaml

# 批次 40 題
./scripts/run_all_tests.sh config.yaml
```

**config.yaml `api_key`**：一般 **不必** 加引號；含特殊字元時用雙引號 `"..."`。

### Token 用量本地記錄

每次呼叫 LLM 會把用量寫到本地檔（不需等 OpenAI Console 更新）：

- `output/token_usage.csv`：逐筆紀錄（時間、provider、model、case、prompt/completion/total tokens、request 摘要）
- `output/token_usage.csv.summary.json`：累計總量（含 by-model 分項）

可用環境變數 `CADCONTEST_TOKEN_LOG` 指定 CSV 路徑（summary 會放在同名 `.summary.json`）。兩者皆在 `output/`（已 gitignore）。注意：未命中規則、實際呼叫 LLM 時才會有紀錄。

---

## 七、目錄結構（精簡）

```
cadcontest/
├── cada1089_alpha          # 入口
├── config.yaml             # LLM 設定（gitignore）
├── python/
│   ├── main.py
│   ├── eda/                # 後端
│   └── agent/              # 前端
├── testcase/test01..40/    # 輸入
├── output/testNN/          # 輸出 log + *_out.v
├── docs/                   # 競賽 PDF + 本文件
└── scripts/                # 批次腳本
```

---

## 八、下一步建議（優先順序）

1. [x] 補跑 **test39** 至 20/20 並產生 `test39_out.v`（2026-06-18 完成，40/40 全通過）  
2. [ ] 抽樣核對 test21（fanout≤4）、test30（depth 優化）等變換題的 **功能等價**  
3. [ ] 針對 test12 做 **parser / 載入快取** 優化  
4. [ ] 整理尚未被規則覆蓋的 prompt 句式，擴充 `handler.py`  
5. [ ] 準備 alpha 提交：Docker / 依賴清單 / README 給評測方  

---

## 九、參考文件

- `docs/A_20260212.pdf` — 競賽說明  
- `docs/Problem A_QA_0417.pdf` — Q&A  
- `testcase/README.md` — sample 說明  
