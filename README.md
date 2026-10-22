# PrimeVul / PairVul 线上实验包（最后一轮）

所有条件使用同一个大模型和同一套设置：`qwen3.8-max-0902`，思考开启，流式输出，temperature 0，seed 20261009，输出上限 8192。

- 提示词全部预先生成并冻结在 `prepared/` 和 `pairvul/prepared/` 中，SHA-256 记录在 `manifest.json` 里，请不要修改。
- 所有检索类条件的知识库都是完整的官方训练集：PrimeVul 3,789 个修复对，PairVul 2,317 个修复对。
- 所有条件都必须开启思考模式：公共参数里的 `--thinking on` 不要删掉，也不要改成别的值。上一轮的 direct 和 VulTrial 也是在思考模式下跑的，本轮必须一致。
- 不需要在开发集上试跑。先做一次很小的小样本检查（第 0 步），通过后直接跑全量。

## 这一轮包括哪三组实验

### 实验一：主实验（PrimeVul，435 对）

目的：检验我们的方法在同一个模型上是否比基线判得更准。

| 条件 | 是什么 | 本轮是否运行 |
|---|---|---|
| `graph_diff_v2` → `verify_graph_diff_v2` | 我们的方法，分两步：<br>1. 锚点检索取 3 个历史修复，以修复前后的 diff 附在目标函数之后，让模型判断；<br>2. 保护核查：只对第一步判为有漏洞的函数再问一次，其余沿用第一步的结果 | 运行 |
| `direct` | 基线：同一个模型，只给目标函数，让它先推理再下结论（CoT） | 上一轮已跑 |
| `vultrial` | 基线：VulTrial（ICSE 2026，模拟法庭的多智能体方法），在同一个模型上复现 | 上一轮已跑 |

### 实验二：消融实验（PrimeVul，435 对）

目的：每次只改动方法的一个部分，看这个部分有没有起作用。

| 消融 | 条件 | 和谁比 | 本轮是否运行 |
|---|---|---|---|
| 去掉保护核查 | `graph_diff_v2`（第一步的结果） | 我们的方法 | 主实验已包含，不需要另跑 |
| 锚点检索换成 BM25 整函数检索 | `graph_diff_text_v2` | `graph_diff_v2` | 运行 |
| diff 换成 JSON 子图（检索结果相同） | `graph_hint_v2` | `graph_diff_v2` | 运行 |
| 去掉防误判提示 | `graph_diff_v2_noguard` | `graph_diff_v2` | 运行 |

### 实验三：泛化实验（PairVul，586 对，在 `pairvul/` 目录）

目的：在另一个数据集上检验方法是否仍然有效。PairVul 是 Vul-RAG 论文的基准，代码来自 Linux 内核，涉及 10 个 CWE，共 1,172 个函数。

条件：只运行我们的方法，即 `graph_diff_v2` → `verify_graph_diff_v2` 两步。

## 准备

1. 更新仓库：

   ```bash
   git pull
   ```

   如果是第一次下载：

   ```bash
   git clone https://github.com/hhcyb/primevul-online-eval.git
   cd primevul-online-eval
   ```

2. 把上一轮的 `results/` 文件夹放到仓库根目录。里面应有 direct 和 vultrial 的 `predictions_*.jsonl` 和 `run_config_*.json`，打分时会和本轮结果放在一起比较。`results/` 不在版本控制里，`git pull` 不会改动它。

3. 设置公共参数。接口地址和 API Key 的环境变量名请沿用上一轮：

   ```bash
   M="--model qwen3.8-max-0902 --api-base <上一轮的接口地址> --api-key-env <上一轮的变量名> --thinking on --stream on --workers 8"
   ```

   需要 Python 3.8 或以上，不需要安装任何第三方库。

## 运行

### 第 0 步：小样本检查（正式运行前做一次，在仓库根目录运行）

```bash
python smoke_test.py $M
```

- 本轮每个条件只跑前 2 个函数（一对），PrimeVul 和 PairVul 都包括，一共约 14 次调用。
- 结果写在单独的 `results_smoke/` 和 `pairvul/results_smoke/` 中，不会混进正式结果。
- 检查内容：接口能连通、每个函数都拿到了判定、每次调用都开启了思考模式。
- 最后一行显示 `Smoke test passed` 就可以开始正式运行；显示 `FAILED` 请不要开始，把输出发给我们。
- 运行中出现 `... without a stage-1 answer (skipped)` 是正常的，因为小样本只有 2 个函数。

### PrimeVul：实验一和实验二（在仓库根目录运行）

第 2 条（保护核查）必须等第 1 条全部跑完、并且没有失败的调用后再开始；提前开始时程序会拒绝运行并提示。其余各条之间没有依赖。

```bash
# 实验一：我们的方法（两步）
python online/run_online.py run --condition graph_diff_v2 $M
python online/run_online.py run --condition verify_graph_diff_v2 --stage1 results/predictions_graph_diff_v2_qwen3.8-max-0902.jsonl $M
# 实验二：消融
python online/run_online.py run --condition graph_diff_text_v2 $M
python online/run_online.py run --condition graph_hint_v2 $M
python online/run_online.py run --condition graph_diff_v2_noguard $M
```

打分：

```bash
python online/run_online.py score --baseline direct_qwen3.8-max-0902 > results/score_vs_direct.txt
python online/run_online.py score --baseline graph_diff_v2_qwen3.8-max-0902 > results/score_vs_graph_diff_v2.txt
```

第一个文件是实验一（各方法对比 direct），第二个文件是实验二（各消融对比 `graph_diff_v2`）。

### PairVul：实验三（在 `pairvul/` 目录运行）

```bash
cd pairvul
python online/run_online.py run --condition graph_diff_v2 $M
python online/run_online.py run --condition verify_graph_diff_v2 --stage1 results/predictions_graph_diff_v2_qwen3.8-max-0902.jsonl $M
python online/run_online.py score --baseline graph_diff_v2_qwen3.8-max-0902 > results/score.txt
```

## 建议的运行安排

开 3 个终端窗口同时运行（共 24 路并发，与上一轮相同），每个窗口内按顺序执行：

| 窗口 | 依次运行 | 调用次数 | 预计耗时 |
|---|---|---:|---:|
| 1 | PrimeVul `graph_diff_v2` → `verify_graph_diff_v2` → `graph_diff_v2_noguard` | 约 2,430 | 约 41 小时 |
| 2 | PairVul `graph_diff_v2` → `verify_graph_diff_v2` | 约 2,100 | 约 36 小时 |
| 3 | PrimeVul `graph_diff_text_v2` → `graph_hint_v2` | 1,740 | 约 30 小时 |

全部跑完约需 1.5–2 天。耗时按上一轮的实测速度估算：每个窗口（8 路并发）每小时约完成 59 次调用，平均每次调用约 8 分钟，主要花在思考上。

## 用量与费用估算

| 项目 | 估算 |
|---|---:|
| 调用次数 | 约 6,270 次（另有小样本检查约 14 次） |
| 输入 tokens | 约 1,700 万 |
| 输出 tokens（含思考） | 约 1.07–1.25 亿 |
| 费用（按百炼公开价：输入 12 元、输出 36 元每百万 tokens） | 约 4,000–4,700 元 |

- 输出按上一轮实测估算：每次调用平均约 2 万个输出 tokens，几乎都是思考过程，中位数约 1.7 万；个别调用超过 10 万。
- 费用的 90% 以上来自输出。PairVul 的函数较短，实际用量可能偏低。
- 以上是按公开价的估算，实际以接口账单为准。

## 注意事项

- 中途断了，或者有失败的调用，用同一条命令再运行一次即可：已完成的会跳过，只重试失败的部分。
- 重试：每次调用遇到网络错误、HTTP 429 或 5xx 时会自动重试，最多 8 次，间隔逐渐加长（约 10 分钟）；HTTP 429 会按接口返回的等待时间等待。网络中断超过约 10 分钟时，这期间的调用会记为失败，事后用同一条命令再运行一次即可。
- 并发：每条命令默认 8 路并发。建议同时开的窗口不超过 3 个；如果频繁出现 HTTP 429，减少窗口数，或者加 `--workers 4`（之后同一条命令都要加）。
- 想停下时按一次 Ctrl+C：程序会取消排队中的调用，等正在进行的调用（最多 8 个）完成并保存后退出。
- 同一条命令不要在两个窗口里同时运行，程序会拒绝第二个。
- 如果改了任何参数，程序会拒绝在原来的结果文件上续跑，这时需要加 `--tag` 另起名字。
- 每 20 个函数显示一次进度和预计剩余时间。
- 跑完后，请把根目录的 `results/` 和 `pairvul/results/` 一起打包发回。

常见报错的处理（同一组实验的所有命令都要加上同样的参数）：

| 报错 | 处理 |
|---|---|
| `HTTP 400`，提到 `seed` | 加 `--seed -1` |
| `HTTP 400`，提到 `enable_thinking` | 不要改成 `--thinking default` 或 `off`，请先停下来联系我们 |
| `HTTP 429`（请求太频繁） | 降低并发，例如 `--workers 4` |

## 打分各列的含义

| 列 | 含义 |
|---|---|
| P-C | 漏洞版判为有漏洞、修复版判为安全，两侧都对，主要指标 |
| P-V / P-B | 两侧都判有漏洞 / 都判安全 |
| P-R | 两侧都判反 |
| fail | 至少一侧没有拿到有效回答 |
| C-R | P-C 减 P-R，衡量真正的区分能力 |
| vs baseline | 相对基线改对和改错的 pair 数，以及精确 McNemar 检验的 p 值 |
