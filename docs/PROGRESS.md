# ICCAD 2026 Problem A — 專案進度與待辦

> **專案**：LLM-Assisted Netlist Exploration and Transformation  
> **執行檔**：`./cada0001_alpha -config config.yaml`  
> **最後更新**：2026-05-23

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
- 批次模式可關閉 LLM：`CADCONTEST_NO_LLM=1`（規則匹配，不耗 API）
- `config.yaml` 已加入 `.gitignore`

### 2.4 Sample testcase 執行進度（40 題）

> 判定：**完整** = 回應數 = prompt 行數 且 有 `testNN_out.v`

| 狀態 | 數量 | Testcase |
|------|------|----------|
| ✅ 完整 | **39** | test01–test38、test40 |
| ⚠️ 未完成 | **1** | test39（11/20 則回應，無 `test39_out.v`） |

**test12 備註**：netlist 極大（約 **91,583 gates**），單次解析約 **165 秒**；完整跑完需數小時級時間，目前已有 log 與 out.v，但回應數可能與 prompt 行數不一致（曾多次重跑累積）。

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
| test12 | 17* | 11 | ✅ | 超大電路，耗時極長 |
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
| test39 | 11 | 20 | ❌ | **待補跑** |
| test40 | 20 | 20 | ✅ | 完整 |

\* test12 回應數 > prompt 行數：可能為多次批次重跑所致，需人工核對 log 是否連續 id 1–11。

---

## 四、待解決問題

### 🔴 高優先

| # | 問題 | 影響 | 建議方向 |
|---|------|------|----------|
| 1 | **test39 未完成**（11/20，無 out.v） | 40 題中缺 1 題完整輸出 | 單獨重跑：`cat testcase/test39/prompt.txt \| ./cada0001_alpha -config config.yaml` |
| 2 | **超大 netlist 效能**（test12：91k gates，解析 ~165s） | 逾時、批次中斷 | 優化 parser；或快取已解析 DAG；大電路分析走快速路徑 |
| 3 | **答案正確性未對標官方** | 有跑完 ≠ 有得分 | 需對照評測腳本 / golden answer（若公布）做 regression |

### 🟡 中優先

| # | 問題 | 影響 | 建議方向 |
|---|------|------|----------|
| 4 | 批次 **300s timeout** 對大題不夠 | test12/14/33 等曾 `exit 124` | 腳本已改 600s；大題可單獨跑、不設 timeout |
| 5 | **路徑完整枚舉** 在大電路上不可行 | Contest 若要求列舉所有 path 可能答錯 | 已對 >15k gates 改為「存在性 + 說明跳過枚舉」；需確認評測是否接受 |
| 6 | **規則匹配覆蓋率** | 未匹配時才呼叫 LLM | 補齊 `handler.py` 規則；或強化 Tool Spec + LLM 規劃 |
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
cat testcase/test01/prompt.txt | ./cada0001_alpha -config config.yaml

# 不呼叫 LLM
export CADCONTEST_NO_LLM=1
cat testcase/test01/prompt.txt | ./cada0001_alpha -config config.yaml

# 批次 40 題
./scripts/run_all_tests.sh config.yaml
```

**config.yaml `api_key`**：一般 **不必** 加引號；含特殊字元時用雙引號 `"..."`。

---

## 七、目錄結構（精簡）

```
cadcontest/
├── cada0001_alpha          # 入口
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

1. [ ] 補跑 **test39** 至 20/20 並產生 `test39_out.v`  
2. [ ] 抽樣核對 test21（fanout≤4）、test30（depth 優化）等變換題的 **功能等價**  
3. [ ] 針對 test12 做 **parser / 載入快取** 優化  
4. [ ] 整理尚未被規則覆蓋的 prompt 句式，擴充 `handler.py`  
5. [ ] 準備 alpha 提交：Docker / 依賴清單 / README 給評測方  

---

## 九、參考文件

- `docs/A_20260212.pdf` — 競賽說明  
- `docs/Problem A_QA_0417.pdf` — Q&A  
- `testcase/README.md` — sample 說明  
