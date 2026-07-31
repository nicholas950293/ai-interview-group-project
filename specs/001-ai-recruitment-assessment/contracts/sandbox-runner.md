# 契約：SandboxRunner（沙箱執行介面）

**對應需求**：FR-036～FR-048 | **憲章依據**：原則 VI（不可妥協）
**研究決策**：[research.md](../research.md) R-001

本介面是系統中唯一執行不受信任程式碼的位置。所有實作皆必須滿足下列契約；
`FakeSandboxRunner` 用於離線測試，`DockerSandboxRunner` 為正式實作。

---

## 介面定義

```python
class SandboxRunner(Protocol):
    async def run(self, request: ExecutionRequest) -> ExecutionResult: ...
    async def health_check(self) -> bool: ...
```

### `ExecutionRequest`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `code` | `str` | 應徵者提交的原始碼。**不受信任** |
| `language` | `Language` | `javascript` / `python` / `go` / `java` / `cpp` |
| `stdin` | `str` | 標準輸入 |
| `limits` | `ResourceLimits` | 資源上限，見下 |

### `ResourceLimits`（預設值）

| 欄位 | 預設 | 對應憲章原則 VI 條款 |
|------|------|---------------------|
| `cpu_seconds` | 10 | CPU 時間上限 |
| `memory_mb` | 512 | 記憶體用量上限 |
| `wall_clock_seconds` | 30 | 牆鐘時間上限（含編譯） |
| `max_processes` | 64 | 程序數量上限 |
| `max_output_bytes` | 1048576 | 輸出大小上限 |

實作**不得**接受高於上述預設的值。放寬任一上限須依憲章原則 VI 於
[plan.md](../plan.md) 記錄並附風險評估。

### `ExecutionResult`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `stdout` | `str` | 超過上限時截斷 |
| `stderr` | `str` | 超過上限時截斷 |
| `exit_code` | `int \| None` | 遭強制中止時為 `None` |
| `duration_ms` | `int` | 牆鐘耗時 |
| `peak_memory_kb` | `int \| None` | |
| `termination_reason` | `TerminationReason` | 見下 |
| `truncated` | `bool` | 輸出是否被截斷 |

### `TerminationReason`

| 值 | 意義 | 來源 FR |
|----|------|--------|
| `COMPLETED` | 正常結束（含非零退出碼） | FR-044 |
| `TIMEOUT` | 超過 CPU 或牆鐘上限 | FR-040 |
| `MEMORY_LIMIT` | 超過記憶體上限 | FR-040 |
| `PIDS_LIMIT` | 超過程序數上限 | FR-040 |
| `OUTPUT_LIMIT` | 超過輸出上限 | FR-040 |
| `COMPILE_ERROR` | 編譯失敗，訊息置於 `stderr` | FR-045 |
| `SANDBOX_UNAVAILABLE` | 沙箱不可用 | FR-047 |

---

## 行為契約（所有實作皆須滿足）

1. **絕不拋出例外給呼叫端**。所有失敗情境皆以 `termination_reason` 表達。
   呼叫端必須能在任何情況下取得 `ExecutionResult`（FR-045、FR-047）。
2. **絕不回傳部分結果後才失敗**。回傳值必為完整且一致的 `ExecutionResult`。
3. **牆鐘逾時由呼叫端外部計時強制**，不得依賴被執行程式碼的自我約束。
4. **輸出以串流讀取**，達上限即停止讀取並中止執行，不得先緩衝完整輸出再截斷——
   否則 `max_output_bytes` 無法防止記憶體耗盡。
5. **併發由呼叫端以 `asyncio.Semaphore(10)` 限制**（FR-046）。介面本身不做排隊。
6. `health_check()` 回傳 `False` 時，呼叫端必須降級為「接受提交但不執行」，
   **不得**改以未隔離的方式執行（憲章原則 VI）。

---

## `DockerSandboxRunner` 實作要求

每次執行啟動一個拋棄式容器，參數固定如下。這張表是安全套件的斷言依據——
每一列都必須有對應的測試。

| Docker 參數 | 值 | 驗證方式 |
|------------|-----|---------|
| `--network` | `none` | 執行嘗試對外連線的程式碼，斷言失敗 |
| `--read-only` | 啟用 | 執行寫入 `/etc` 的程式碼，斷言失敗 |
| `--tmpfs` | `/work:rw,size=64m` | 執行寫入 `/work` 的程式碼，斷言成功 |
| `--memory` | `512m` | 執行配置 1 GB 的程式碼，斷言 `MEMORY_LIMIT` |
| `--memory-swap` | `512m`（等同禁用 swap） | 同上 |
| `--cpus` | `1.0` | |
| `--pids-limit` | `64` | 執行 fork bomb，斷言 `PIDS_LIMIT` |
| `--cap-drop` | `ALL` | |
| `--security-opt` | `no-new-privileges` | |
| `--user` | 非 root 固定 UID（如 `65534`） | 執行 `id`，斷言非 0 |
| `--rm` | 啟用 | 執行後斷言容器不存在 |
| `--runtime` | `runsc`（若可用） | 選用，見 R-001 |

**工作目錄**：原始碼寫入 `/work`（tmpfs），編譯產物亦置於該處。
容器結束時 tmpfs 隨之消滅，滿足「用後即棄」（FR-042）。

**映像檔**：每種語言一個最小映像檔，定義於 `sandbox/<language>/Dockerfile`。
語言版本必須固定並向應徵者顯示（FR-037）。映像檔內**不得**包含編譯器以外的
網路工具、套件管理器或憑證。

---

## 安全套件必測項目

以下測試以 `@pytest.mark.security` 標記，需本機 Docker（[research.md](../research.md) R-008）。
對應憲章「安全關卡」的三類要求。

### 網路阻斷

- 對外 HTTP 請求必須失敗
- DNS 解析必須失敗
- 對宿主 IP 的連線必須失敗

### 資源耗盡中止

- 無窮迴圈 → `TIMEOUT`，且中止耗時不超過牆鐘上限 + 5 秒
- 記憶體配置超限 → `MEMORY_LIMIT`
- fork bomb → `PIDS_LIMIT`，且宿主程序數不受影響
- 無限輸出 → `OUTPUT_LIMIT`，且宿主記憶體用量不隨之成長

### 檔案系統存取阻擋

- 讀取 `/etc/passwd` 以外的宿主敏感路徑必須失敗
- 寫入根檔案系統必須失敗
- 寫入 `/work` 必須成功
- 前一次執行在 `/work` 留下的檔案，在下一次執行中必須不存在（FR-042）

### 五語言基準

每種語言各一組「正常執行」與「編譯／語法錯誤」測試，斷言 `COMPLETED`
與 `COMPILE_ERROR` 的判定正確。

---

## `FakeSandboxRunner`（測試替身）

用於預設離線套件。以預先登錄的 `(code, language) → ExecutionResult` 對應表
回傳結果，並支援模擬 `health_check()` 為 `False` 以驗證降級路徑（FR-047）。

**不得**在替身中實作任何真實執行邏輯。
