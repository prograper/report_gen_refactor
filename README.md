# 药学报告自动生成流水线（Python）

> Excel 多 Sheet →（LLM 抽取）→ 段落生成 / 变量直填 → Word 报告
> 支持**生成型（generate）**+**直填型（fill）**两种模式并行；带**验证器**与**分层日志**。

---

## ✨ 功能亮点

* **可配置管线**：每个 Sheet 用专属抽取提示词抽关键变量；变量再喂给不同段落生成器或直接填入 Word。
* **两种模式并行**：

  * `generate`：LLM 生成整段文本 → 插入 `{{ 段落ID }}`
  * `fill`：直接把 `{{ Sheet.Field }}` 替换为抽取值（不调用 LLM）
* **验证器（validate 子命令）**：不调用 LLM、不产出文件，预检查

  * 配置结构、文件存在性、Excel-Sheet 对齐
  * 模板占位符（变量/段落）交叉校验
  * **可选“模板模拟渲染”**（StrictUndefined）提前发现未定义变量/语法问题
* **健壮性**：软失败边界、错误收集、类型清洗（`number / array[string] / string`，支持“85%→0.85”）
* **分层日志**：`logs/user.log`（业务可读）/ `system.log`（系统状态）/ `config.log`（调试细节）
* **输出报告**：`configs/output/<报告名>.docx`
  **验证/运行摘要**：`logs/validator_report.json|md`、`logs/run_summary.json`

---

## 📁 目录结构

```text
project-root/
├─ main.py                      # CLI：validate / run
├─ orchestrator.py              # 编排器（薄）
├─ agents/                      # 抽取/生成 Agent（与旧版兼容）
│  ├─ __init__.py               # 触发注册（导入 extract & generate）
│  ├─ registry.py               # register/get 函数
│  ├─ extract_generic.py        # GenericExtractor（表到变量）
│  └─ generate/
│     ├─ __init__.py            # 导入 base 触发注册
│     └─ base.py                # GenericParagraphGenerator（段落生成）
├─ services/                    # 业务步骤
│  ├─ extractor_service.py      # 遍历 Sheet 抽取 + 类型清洗
│  ├─ generator_service.py      # 段落生成 / 直填分发
│  ├─ renderer_service.py       # 渲染输出 Word
│  └─ planner.py                # 执行计划（来自验证结果）
├─ validator/                   # 验证器
│  ├─ validate.py               # 主入口（可被 main 独立调用）
│  ├─ rules.py                  # 各类规则校验
│  ├─ docx_scan.py              # 只提取干净占位符（{{ ... }} 内部）
│  ├─ simulate.py               # *可选* 严格模板模拟渲染
│  └─ report.py                 # 结构化报告输出（JSON/MD）
├─ io_utils/                    # I/O（避免和 stdlib 的 io 冲突）
│  ├─ loaders.py                # 读 YAML/Excel/模板
│  └─ writers.py                # 写 Word/JSON
├─ utils/
│  ├─ resolve.py                # 路径解析 & 嵌套赋值
│  └─ coerce.py                 # 类型清洗（含百分号→小数）
├─ core/
│  ├─ error_collector.py        # 软失败与运行摘要
│  └─ logging_setup.py          # 日志初始化（分层日志）
└─ configs/                     # 业务配置根目录（示例）
   ├─ business_configs/
   │  ├─ sheet_tasks.yaml
   │  └─ paragraph_tasks.yaml
   ├─ prompts/
   │  ├─ extract/...
   │  └─ generate/...
   ├─ template/
   │  └─ report_template.docx
   └─ input/
      └─ your_data.xlsx
```

> ✅ 请确保这些包目录都有 `__init__.py`（可为空）。

---

## 🧩 配置文件说明

### 1) `sheet_tasks.yaml`（每个 Sheet 的抽取任务）

```yaml
fig_sum:
  prompt: extract/extract_pk_params.txt     # 相对于 configs/prompts/
  provider: qwen                            # 可选；默认读取全局/环境
  keys:
    main_time_excretion: string
    average_time_daily_excretion: string

sum_total:
  prompt: extract/extract_subject_info.txt
  keys:
    total_recov_rate_urine_feces: string
    cum_recov_rate_feces: string
    cum_recov_rate_urine: string
    sum_subjects: number                    # 将尝试转 float
```

* **顶层键**必须与 Excel 的 **Sheet 名一致**。
* `keys` 支持类型：`string` / `number` / `array[string]`。
* 值清洗：`number` 支持 `"85%" → 0.85`、去逗号、去空格。

### 2) `paragraph_tasks.yaml`（段落生成/直填）

```yaml
# 生成型：LLM 生成整段 → Word 用 {{ Excretion }}
Excretion:
  mode: generate
  prompt: generate/gen_intro.txt            # 相对于 configs/prompts/
  provider: qwen
  keys:
    - sum_total.total_recov_rate_urine_feces
    - sum_total.cum_recov_rate_feces
    - sum_total.cum_recov_rate_urine
    - sum_total.sum_subjects
    - fig_sum.main_time_excretion
    - fig_sum.average_time_daily_excretion

# 直填型：不生成；Word 直接引用变量 {{ sum_total.sum_subjects }}
PKBlock:
  mode: fill
  keys:
    - sum_total.sum_subjects
    - fig_sum.main_time_excretion
```

* **并行模式**：你可以既有 `generate` 段落，也有 `fill` 变量。
* `mode` 省略时规则：有 `prompt` ⇒ `generate`；否则 `fill`。

---

## 📝 Word 模板占位符（docxtpl / Jinja）

* **变量占位符**（直填）：

  ```jinja
  {{ sum_total.sum_subjects }}
  {{ sum_total.cum_recov_rate_urine or '-' }}
  {{ "%.2f"|format(sum_total.sum_subjects) }}
  ```
* **生成段落占位符**（整段文本）：

  ```jinja
  {{ Excretion }}
  {{ Conclusion }}
  ```
* 可**混合使用**，同一模板中并行。
* **注意**：尽量让占位符作为**纯文本**存在，不要被 Word 拆成多个 run（避免识别困难）。

---

## ⚙️ 安装与环境

* Python ≥ 3.10
* 依赖安装：

  ```bash
  pip install pandas docxtpl pyyaml jinja2 openai
  # 以及你所用 LLM 提供商的 SDK（例如 Qwen/通义的 dashscope）
  ```
* 环境变量（示例：Qwen/通义）：

  * Windows（PowerShell）：`$env:DASHSCOPE_API_KEY="sk-..."`
  * Windows（cmd）：`set DASHSCOPE_API_KEY=sk-...`
  * macOS/Linux：`export DASHSCOPE_API_KEY=sk-...`

> 你的 `llm_client.py` 里如支持更多 provider，请按其说明设置对应密钥/base\_url。

---

## 🚦 验证（不耗费 LLM 调用）

```bash
# 默认会执行“模板模拟渲染”（StrictUndefined）
python main.py validate -c ./configs --strict

# 指定 Excel
python main.py validate -c ./configs -i ./configs/input/data.xlsx --strict

# 关闭模板模拟渲染
python main.py validate -c ./configs --no-render
```

输出：

* `logs/validator_report.json` / `logs/validator_report.md`

  * `placeholders.variables`：模板中出现的变量占位符（干净的 `Sheet.Field`）
  * `placeholders.paragraphs`：模板中的段落占位符（简单 ID）
  * `placeholders.others`：其它复杂表达式（仅提示）
  * `simulate_render`: `enabled / ok / error`
* `planned_skips`：建议跳过的 sheet/段落（运行时会采纳）

---

## ▶️ 运行流水线

```bash
# 新命令风格
python main.py run -c ./configs -n 测试文档

# 兼容老用法（无子命令也行）
python main.py -c ./configs -n 测试文档
```

产物：

* `configs/output/测试文档.docx`
* 日志与摘要：`logs/user.log`、`system.log`、`config.log`、`run_summary.json`

---

## 🗂️ 日志与健壮性

* **分层日志**

  * `logs/user.log`：业务可读摘要（抽取值摘要、生成段落摘要、直填值摘要、缺字段）
  * `logs/system.log`：系统状态（流程、I/O、模型调用、警告）
  * `logs/config.log`：调试细节（融合后的 Prompt/Schema、完整生成文本、完整变量 JSON）
* **软失败**

  * 配置错误/缺文件/缺字段 → 记录并**跳过该项**继续执行
  * `fill` 模式缺值 → 自动补 `"-"`，避免模板渲染报错
  * 运行摘要：`logs/run_summary.json`

---

## 🔌 扩展：新增自定义 Agent

* **抽取器**：新增 `agents/extract_xxx.py`，类上用 `@register_extractor`；在 `agents/__init__.py` 导入一下即可。
* **生成器**：在 `agents/generate/` 新增实现并 `@register_generator`；在 `agents/generate/__init__.py` 导入触发注册。

---

## 🛠️ 常见问题（FAQ）

* **`ModuleNotFoundError: 'io' is not a package`**
  你的 I/O 目录不能叫 `io`（与 Python 标准库冲突）。本项目使用 `io_utils/`。
* **“模板变量未定义/语法错误”**
  验证阶段开启“模板模拟渲染”会提前报错（StrictUndefined）。
  检查：变量路径是否 `Sheet.Field`、是否在 `sheet_tasks.yaml` 声明、是否有 `|default('-')` 兜底。
* **“Excel 中不存在 Sheet：xxx”**
  Sheet 名须与 `sheet_tasks.yaml` 顶层键完全一致（区分大小写）。
* **“段落配置为 generate，但模板未使用该占位符”**
  只是提示：你配置了生成段落，但模板没放 `{{ 段落ID }}`。
* **“提示词文件不存在”**
  `sheet_tasks.yaml` / `paragraph_tasks.yaml` 里的 `prompt` 路径是**相对于 `configs/prompts/`** 的。

---

## 📄 许可证

本项目使用 **Apache License 2.0**。
详见根目录 `LICENSE` 文件。

---

## 🤝 联系 & 贡献

* 你可以把验证器单独作为工具使用（CI 前置校验强烈推荐）。
* 欢迎提交 PR：新增抽取/生成 Agent、优化规则、补充示例模板/数据。

