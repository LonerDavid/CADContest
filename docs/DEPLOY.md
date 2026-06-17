# 部署到大會 VM（`scripts/deploy_to_vm.sh`）

把本機專案經 **EDAUnion 跳板** 同步到 ICCAD VM，並（可選）在 VM 上編譯 C++ 擴充、跑 smoke test。

> 在**你自己的 Terminal** 執行。過程是互動式的：會先問 **EDAUnion 密碼**、再問 **VM 密碼**（除非已設好 SSH key）。

## 連線拓樸

```
你的 Mac ──ssh -J──▶ EDAUnion (跳板, port 40061) ──▶ ICCAD VM (cada1089@140.110.214.90)
```

EDAUnion 只是白名單 IP 跳板，不在上面執行任何東西；`-J` 會自動穿透。

## 三種模式

```bash
cd /Users/lonersmac/Developer/cadcontest

# 1) 只同步（純 Python 版；mirror 到 submission，DELETE=1 讓兩邊完全一致）
DELETE=1 MODE=upload ./scripts/deploy_to_vm.sh

# 2) 同步 + C++ 加速（VM 連得到網路時）
./scripts/deploy_to_vm.sh

# 3) 同步 + C++ 加速（VM 無法上網 → 離線把 pybind11 wheel 帶上去編）
MODE=cpp ./scripts/deploy_to_vm.sh
```

| MODE | 動作 |
|------|------|
| `upload` | 只做 rsync |
| `full`（預設） | rsync → 在 VM `pip install pybind11`（需網路）→ `build_ext` → smoke test |
| `cpp` | rsync → 本機 `pip download pybind11` → 經跳板 `scp` 上 VM → 離線安裝 + `build_ext` → smoke test |

## 可調環境變數（預設值）

| 變數 | 預設 | 說明 |
|------|------|------|
| `DEST` | `alpha_test_submission` | VM 上的目標資料夾（相對於家目錄） |
| `DELETE` | `0` | 設 `1` 時 `--delete`，讓目的端與本機**完全一致**（刪多餘檔） |
| `CONFIG` | `config.example.yaml` | smoke test 用的 config |
| `MODE` | `full` | `full` / `upload` / `cpp` |
| `JUMP` / `JUMP_PORT` | `eda26s06@edaunion.ee.ntu.edu.tw` / `40061` | 跳板 |
| `VM_USER` / `VM_HOST` | `cada1089` / `140.110.214.90` | VM |

範例：部署到別的資料夾並完全 mirror
```bash
DEST=beta_test_submission DELETE=1 ./scripts/deploy_to_vm.sh
```

## 同步時排除了什麼（重要）

rsync **不讀 `.gitignore`**，排除清單寫在腳本內。以下不會上傳：

- `config.yaml`（**含 API key，絕不上傳**）、`.venv/`、`output/`、`*.log`、`*_out.v`
- `*.so`（本機 macOS 編的，Linux 用不了；要在 VM 上重編）
- `.git/`、`__pycache__/`、`.DS_Store`、`._*`、`.idea/`、`.vscode/`、`build/`、`*.egg-info/`

## C++ 擴充（`eda_core`）

- 本機的 `eda_core*darwin*.so` 是 **macOS/arm64**，**在 Linux VM 無法載入**，所以不上傳、要在 VM 重編。
- 編譯需要 VM 有 **C++17 編譯器**（`g++`）；學術機常需 `module load gcc`。
- 編不出來也沒關係：`graph.py` 會自動 **fallback 純 Python**，答案正確，只是 hot path 較慢（注意超大電路 vs 300s 上限）。
- 用 `MODE=cpp` 部署到 `alpha_test_submission`，submission 內就會帶**編好的 `eda_core*linux*.so`**。

## config 與評測

- `main.py` 的 `-config` 是**必填**，程式沒有預設路徑。
- smoke test 明確帶 `-config config.example.yaml`；它的 key 是佔位符，**只能跑規則命中的請求**（如 test01）。走 LLM 的請求會因假 key 失敗。
- **官方評測**：大會自己提供 `-config`（含真 key）。submission **不要**放真 key。

## 常見問題

- **問雙重密碼**：正常（跳板 + VM）。想免密碼可設 SSH key + `ssh-copy-id`。
- **`Unmatched '''` / `set: Variable name...`**：VM 登入 shell 是 tcsh；腳本已改用 `bash -s` here-doc，不受影響。
- **`pip` 裝不到套件**：VM 對外網路受限，改用 `MODE=cpp` 離線帶 wheel。
