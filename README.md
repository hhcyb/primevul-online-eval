# PrimeVul / PairVul 线上实验包（最后一轮）

所有条件使用**同一个大模型**和同一套设置：`qwen3.8-max-0902`，思考开启，流式输出，temperature 0，seed 20261009，输出上限 8192。提示词全部**预先生成并冻结**在 `prepared/` 和 `pairvul/prepared/` 中，SHA-256 记录在 `manifest.json` 里，请不要修改。

仓库分两部分，各自独立运行：

- 根目录：PrimeVul 官方配对测试集，435 对，共 870 个函数。
- `pairvul/`：PairVul（Vul-RAG 论文的基准，Linux 内核，10 个 CWE），全部 586 对，共 1,172 个函数。

所有检索类条件的知识库都是**完整的官方训练集**：PrimeVul 3,789 个修复对，PairVul 2,317 个修复对。

## 条件

**PrimeVul（根目录）**

| 条件 | 内容 | 每个函数的调用次数 |
|---|---|---:|
| `graph_diff_v2` | 我们的方法第一步：锚点检索取 3 个历史修复，以修复前后的 diff 呈现，附在目标函数之后 | 1 |
| `verify_graph_diff_v2` | 我们的方法第二步（保护核查）：只对第一步判为有漏洞的函数再调用一次，其余沿用第一步的结果 | 0–1 |
| `graph_diff_text_v2` | 消融：把锚点检索换成 BM25 整函数检索（见文末），其余与 `graph_diff_v2` 相同 | 1 |
| `graph_hint_v2` | 消融：检索结果与 `graph_diff_v2` 相同，但以 JSON 子图呈现，而不是 diff | 1 |
| `graph_diff_v2_noguard` | 消融：去掉 system 提示中的防误判说明，其余与 `graph_diff_v2` 相同 | 1 |
| `zero_shot` | 基线（可选）：Vul-RAG 仓库的基础提示词，逐字使用 | 1 |

`direct`（同模型 CoT）和 `vultrial` 上一轮已经跑过，本轮不再运行，打分时直接使用上一轮的结果。

**PairVul（`pairvul/` 目录）**：只运行我们的方法，即 `graph_diff_v2` 和 `verify_graph_diff_v2` 两步。

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

## 一、PrimeVul（在仓库根目录运行）

第 2 条必须等第 1 条全部跑完再开始；其余各条之间没有依赖，可以并行。

```bash
python online/run_online.py run --condition graph_diff_v2 $M
python online/run_online.py run --condition verify_graph_diff_v2 --stage1 results/predictions_graph_diff_v2_qwen3.8-max-0902.jsonl $M
python online/run_online.py run --condition graph_diff_text_v2 $M
python online/run_online.py run --condition graph_hint_v2 $M
python online/run_online.py run --condition graph_diff_v2_noguard $M
# 可选（看预算）：
python online/run_online.py run --condition zero_shot $M
```

打分：

```bash
python online/run_online.py score --baseline direct_qwen3.8-max-0902 > results/score_vs_direct.txt
python online/run_online.py score --baseline graph_diff_v2_qwen3.8-max-0902 > results/score_vs_graph_diff_v2.txt
```

## 二、PairVul（在 `pairvul/` 目录运行）

```bash
cd pairvul
python online/run_online.py run --condition graph_diff_v2 $M
python online/run_online.py run --condition verify_graph_diff_v2 --stage1 results/predictions_graph_diff_v2_qwen3.8-max-0902.jsonl $M
python online/run_online.py score --baseline graph_diff_v2_qwen3.8-max-0902 > results/score.txt
```

## 调用量估算

| 部分 | 条件 | 调用次数 |
|---|---|---:|
| PrimeVul | graph_diff_v2、graph_diff_text_v2、graph_hint_v2、graph_diff_v2_noguard | 各 870 |
| PrimeVul | verify_graph_diff_v2 | 约 700 |
| PrimeVul | zero_shot（可选） | 870 |
| PairVul | graph_diff_v2 | 1,172 |
| PairVul | verify_graph_diff_v2 | 约 900 |

## 注意事项

- 中途断了，或者有失败的调用，用同一条命令再运行一次即可：已完成的会跳过，只重试失败的部分。
- 如果改了任何参数，程序会拒绝在原来的结果文件上续跑，这时需要加 `--tag` 另起名字。
- 每 20 个函数显示一次进度和预计剩余时间。
- 跑完后，请把根目录的 `results/` 和 `pairvul/results/` 一起打包发回。

常见报错的处理（同一组实验的所有命令都要加上同样的参数）：

| 报错 | 处理 |
|---|---|
| `HTTP 400`，提到 `seed` | 加 `--seed -1` |
| `HTTP 400`，提到 `enable_thinking` | 加 `--thinking default` |
| `HTTP 429`（请求太频繁） | 降低并发，例如 `--workers 4` |

## 打分各列的含义

| 列 | 含义 |
|---|---|
| P-C | 漏洞版判为有漏洞、修复版判为安全，两侧都对，**主要指标** |
| P-V / P-B | 两侧都判有漏洞 / 都判安全 |
| P-R | 两侧都判反 |
| fail | 至少一侧没有拿到有效回答 |
| C-R | P-C 减 P-R，衡量真正的区分能力 |
| vs baseline | 相对基线改对和改错的 pair 数，以及精确 McNemar 检验的 p 值 |

## 我们的方法：提示词是怎样生成的

- **锚点检索**：用 Joern 为每个训练修复对的修复前后版本建代码属性图，取修复改动的节点作为锚点。过滤掉低信息锚点（如 `i++`、`return -1`）和在超过 1% 的训练修复中都出现的代码，再用 `qwen3-embedding:8b` 向量化。目标函数的候选操作按稀有度依次作为查询，取最近的 32 个锚点，汇总成 5 个修复对，最终保留前 3 个。
- **diff 呈现**：每个修复对渲染为最多 60 行的 unified diff，与匹配锚点相关的改动块放在最前面。没有检索结果的函数使用与 `direct` 完全相同的提示词。
- **保护核查**：对第一步判为有漏洞的函数，再问一次被指出的危险操作在目标函数中是否已有保护；核查调用失败时沿用第一步的判定。

## 基线的复现说明

- **BM25 整函数检索（`graph_diff_text_v2` 使用）**：检索部分沿用 Vul-RAG（TOSEM）作者发布的仓库 `KnowledgeRAG4LLMVulD/KnowledgeRAG4LLMVulD` 中 `vulnerability_detect.py --retrieve_by_code` 的实现：spaCy `en_core_web_sm` 分词加 `rank_bm25.BM25Okapi`（默认参数），对每个训练修复对的修复前代码建索引，取前 20 条，按 CVE 去重，保留前 3 对；之后用与 `graph_diff_v2` 相同的 diff 渲染和提示词。
- **零样本（`zero_shot`）**：逐字使用同一仓库 `VUL-RAG/src_baseline/baseline_detect.py` 的 `prompt_type 0`。
- **零样本的答案解析**：取最后一个 `<result>…</result>`，含 YES 判为有漏洞，含 NO 判为无漏洞。没有标签时追问一次，仍然失败则记为失败。
- **VulTrial**（上一轮已跑）：提示词从作者公开的复现包（figshare `1514bc9a7aa64b46d94e`，CC BY 4.0）中原样提取，保存在 `online/vultrial_prompts.json`，流程和判定规则与原实现一致。
