# ICCAD 2026 Problem A — 專案進度與待辦

> **專案**：LLM-Assisted Netlist Exploration and Transformation  
> **團隊**：Team 1089 — Yu-Sheng Liao (B12901032), Cheng-Yeh Yang (B12901043)  
> **執行檔**：`./cada1089_alpha -config config.yaml`  
> **最後更新**：2026-06-23

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

**額外工具（`extras.py`）**
- 計數 / 查詢、結構列表、路徑 / 圖論類工具（約 75 個工具，已寫入 `tool_spec.py`）

### 2.3 工程化

- 輸出統一目錄：`output/testNN/`（`.log` + `*_out.v`）
- 批次腳本：`scripts/run_all_tests.sh`、`scripts/run_tests_range.sh`、`scripts/summarize_results.sh`
- **Token 用量本地記錄**：`python/agent/usage_log.py` → `output/token_usage.csv` + `.summary.json`
- **LLM fallback 評測**：`scripts/llm_fallback_eval.py`（`CADCONTEST_FORCE_LLM=1` 強制全走 LLM，與規則輸出對比）
- **VM 部署**：`scripts/deploy_to_vm.sh`（經 EDAUnion 跳板 rsync；模式：`upload` / `full` / `cpp` / `uv`）；用法見 `docs/DEPLOY.md`
- **C++ 加速**：`cpp/eda_core/`（pybind11）；VM 上以 `MODE=uv` 建 `.venv` + 可移植 `-O3` 編譯 `.so`
- `config.yaml` 已加入 `.gitignore`；`.claude/`、`abc.history` 亦已忽略

### 2.4 LLM fallback 全量評測

> 以規則輸出為 golden，強制全部走 LLM（2026-06-18）

- 全 40 題：**434/487 (89%) 命中**，mismatch=50，err=3
- 剩餘分歧：工具近義選擇、gate 名 vs signal 名、transform 後計數 vs 確認訊息等
- 結論：維持 **規則優先 + LLM fallback** 的 hybrid 設計

### 2.5 PDF 規格合規（A_20260212.pdf）

| 要求 | 狀態 |
|------|------|
| 執行檔 `cada1089_alpha -config <path>` | ✅ |
| flat Verilog + 原語 + dff + bus + 常數 | ✅ |
| stdin 逐行、`#RESPONSE/#END` 格式 | ✅ |
| LLM config（gpt-4o-mini / claude-haiku-4-5） | ✅ |
| Tool Spec 注入 system prompt | ✅ |
| 基本 ≤60s / 其他 ≤300s | ⚠️ 多數遠低於上限；test39 ~105s |

### 2.6 Sample testcase 執行進度（40 題）

> 判定：**完整** = 回應數 = prompt 行數 且 有 `testNN_out.v`  
> 最近一次完整批次：2026-06-18，總耗時約 6.5 分鐘

| 狀態 | 數量 | Testcase |
|------|------|----------|
| ✅ 完整 | **40** | test01–test40 |
| ⚠️ 未完成 | **0** | — |

**最慢題目**：test39（~105s）、test12（~48s）、test35（~48s）、test34（~47s）、test37（~31s）。

**test12 備註**：netlist 極大（約 **91,583 gates**）；C++ 加速後約 48s 完成 11/11。

### 2.7 VM 部署（alpha_test_submission）

| 項目 | 狀態 |
|------|------|
| rsync 至 VM `alpha_test_submission/` | ✅ |
| uv standalone Python 3.12.13 + 專案 `.venv` | ✅ |
| 依賴安裝（pyyaml / openai / anthropic / pybind11） | ✅ |
| C++ `eda_core*.so` 編譯（可移植 `-O3`） | ✅ |
| 執行時 `import eda_core`（CPP_OK） | ✅ |
| test01 煙霧測試 | ✅ |

### 2.8 課程期末繳交（Final Project）

| 項目 | 狀態 | 備註 |
|------|------|------|
| `README.md`（繳交目錄說明 + 重現步驟） | ✅ | 2026-06-21 更新 |
| `docs/report.tex`（IEEE 格式英文報告） | ✅ | 作者已填入；需 compile 成 PDF |
| `docs/final_project_submission_guidelines.pdf` | ✅ | 繳交規範已對照 |
| Presentation slides | ⬜ | 需放入 ZIP（B 項） |
| ZIP 打包（`B12901032_B12901043.zip`） | ⬜ | 截止 2026-06-26 23:59 |

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

### 🔴 高優先（期末繳交）

| # | 問題 | 建議方向 |
|---|------|----------|
| 1 | **report.tex → PDF** | Overleaf 或本地 TeX 編譯 |
| 2 | **簡報 slides 更新** | 放入 ZIP 的 B 項 |
| 3 | **ZIP 打包** | 依 `B12901032_B12901043.zip` 命名，<10 MB |

### 🟡 中優先（競賽 / 品質）

| # | 問題 | 建議方向 |
|---|------|----------|
| 4 | **答案正確性未對標官方 golden** | 有跑完 ≠ 有得分；若公布 golden 做 regression |
| 5 | **變換品質 / 優化 cost** | 評分看 cost ratio；可考慮 ABC 整合到 transform 路徑 |
| 6 | **規則 / LLM 剩餘 11% 分歧** | 持續補 `handler.py` 規則或強化 Tool Spec |
| 7 | **超大 netlist**（test12） | 已靠 C++ 改善；可再加 parser 快取 |

### 🟢 低優先 / 維護

| # | 問題 | 建議方向 |
|---|------|----------|
| 8 | Verilog writer 與 benchmark 格式不完全一致 | 評測若只檢功能可接受 |
| 9 | ABC bridge 尚未接入主 transform 路徑 | 需要時在 `transform.py` 呼叫 |
| 10 | API key 安全 | 勿 commit `config.yaml` |

---

## 五、已知技術限制

1. **組合邏輯 DAG**：DFF Q 視為額外 PI，不處理時序等價。  
2. **功能等價**：窮舉 PI（≤18–20 bit），更大則隨機抽樣。  
3. **路徑枚舉**：上限 50 條 / 50k 步；超大電路改 BFS 存在性回答。  
4. **變換驗證**：與變換前 snapshot 比等價；與「最初載入」比需呼叫 `verify_equivalence`。  
5. **VM 依賴**：C++ 加速需 uv 管理的 Python 3.12 + 編譯出的 `.so`；純 Python fallback 仍可用。

---

## 六、如何本地測試

```bash
cd cadcontest
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # 填入 api_key
chmod +x cada1089_alpha

# 單題
cat testcase/test01/prompt.txt | ./cada1089_alpha -config config.yaml

# 批次 40 題
./scripts/run_all_tests.sh config.yaml

# LLM fallback 評測（全 40 題）
python scripts/llm_fallback_eval.py 01-40

# VM 部署（本機終端，需輸入跳板 + VM 密碼）
MODE=uv DELETE=1 scripts/deploy_to_vm.sh
```

### Token 用量

- `output/token_usage.csv`：逐筆 LLM 呼叫紀錄  
- `output/token_usage.csv.summary.json`：累計摘要  
- 環境變數 `CADCONTEST_TOKEN_LOG` 可自訂 CSV 路徑

---

## 七、目錄結構（精簡）

```
cadcontest/
├── cada1089_alpha          # 入口（優先 .venv，否則 newest Python ≥3.7）
├── config.yaml             # LLM 設定（gitignore）
├── setup.py                # C++ extension build
├── cpp/eda_core/           # pybind11 加速
├── python/
│   ├── main.py
│   ├── eda/                # 後端
│   └── agent/              # 前端（含 usage_log.py）
├── testcase/test01..40/
├── output/testNN/          # log + *_out.v
├── docs/
│   ├── report.tex          # 期末報告（IEEE）
│   ├── DEPLOY.md
│   ├── PROGRESS.md         # 本文件
│   └── *.pdf               # 競賽 / 繳交規範
└── scripts/                # 批次、部署、LLM eval
```

---

## 八、下一步建議（優先順序）

1. [ ] 將 `docs/report.tex` 編譯為 PDF（C 項）  
2. [ ] 更新並放入 presentation slides（B 項）  
3. [ ] 打包 `B12901032_B12901043.zip`（A–E 五項齊全）  
4. [ ] 確認 Individual Contributions 段落與實際分工一致  
5. [ ] （選做）抽樣核對變換題功能等價；優化 cost 以提升競賽分數  

---

## 九、參考文件

- `docs/A_20260212.pdf` — ICCAD 2026 Problem A 競賽說明  
- `docs/final_project_submission_guidelines.pdf` — 課程期末繳交規範  
- `docs/report.tex` — 專案報告（IEEE LaTeX）  
- `docs/DEPLOY.md` — VM 部署說明  
- `README.md` — 繳交用目錄與重現步驟  
- `testcase/README.md` — sample 說明  
