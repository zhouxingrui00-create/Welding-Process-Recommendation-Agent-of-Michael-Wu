# 铝合金焊接工艺推荐智能体

## 6A01 专项材料模块

本阶段只建立数据结构、读取接口和页面。**6A01 性能记录、焊接案例、文献记录均为空，没有新增实验数值，也没有训练预测模型。** 原有 `materials.json` 和工艺参数种子库保留，6061、6063、5083、5052、2024、7075 继续使用原有路径。

启动 `python -m streamlit run app.py`，侧栏进入 **6A01专项分析**，可以查看材料信息、三类记录数量、已有资料涉及的方法、模型状态和原始资料。在主页面选择 6A01 后，可填写实际材料状态，也可留空表示未知。

### 文件结构与字段

```text
data/materials/
├── materials.json          # 原有材料种子库
└── 6A01/
    ├── material.json       # 牌号信息与材料档案
    ├── properties.json     # 母材/接头性能与组织记录
    ├── welding_cases.json  # 实际焊接实验案例
    └── literature.json     # 文献条目与可追溯摘要
```

`material.json` 是单个对象。其余三个文件使用 `{"schema_version": "1.0", "record_template": {...}, "records": []}` 格式。`record_template` 是空字段说明，不参与查询或计数；真实资料写入 `records` 数组。所有业务字段可省略或设为 `null`，集合也可为 `null` 或空数组。不要用 `0` 代替缺失的实测值。

| 字段 | 含义及填写约定 |
| --- | --- |
| `id` | 本地唯一记录编号，建议填写，便于追溯 |
| `alloy` | 材料牌号；本目录为 6A01，允许为空；显式填写其他牌号的集合记录会跳过并提示 |
| `temper` | 原始材料状态，未知时为 null，不自动填 T6 |
| `chemical_composition` | 成分对象：按元素保存原始值、单位、测定/标准依据，未知为 null |
| `thickness_mm` | 真实厚度，数值，单位 mm；未知为 null |
| `welding_method` | 方法名称；如 TIG、MIG、激光焊、FSW，也可填其他名称 |
| `welding_parameters` | 参数对象或数组；各项保留名称、值、单位、设备和适用条件 |
| `microstructure` | 组织描述或对象，可附区域、观察方法、图像路径 |
| `mechanical_properties` | 性能对象或数组，保留试验项目、值、单位、试样位置、试验条件 |
| `defects` | 缺陷描述或对象，保留类型、位置、检测方法；null 表示未知，不表示无缺陷 |
| `source` | 来源对象，可包含 title、authors、year、url、doi、report_id、page、file_path、note |

`material.json` 另预留 `series`、`supported_tempers` 和 `supported_welding_methods`；仅填写有资料支持的内容。`literature.json` 另预留 `title`、`summary`。嵌套对象允许逐项为 null，扩展字段会保留。读取器负责容错与查询，不替代成分、单位或实验真实性审核。

### 未来如何导入真实 6A01 数据

1. 整理原始试验记录、报告或文献，确认材料牌号和各字段来源。
2. 选择对应 JSON 文件，把其中 `record_template` 复制为 `records` 的一个对象，按原始资料填写；没有的数据保持 null。模板本身留在 `record_template` 中，不要把空模板批量加入 `records`。
3. 母材和接头的性能可分别作为 `properties` 记录，用扩展字段注明试样区域。每次真实焊接实验保存为独立 `welding_cases` 记录；文献摘要保存到 `literature`。相关条目可用自定义 `case_id`、`literature_id` 关联，读取器会保留这些字段。
4. 在 `source` 中保存报告编号、页码、DOI 或原文位置。来源缺失也能读取，但查询上下文会标记“来源待补充”。不要把 LLM 生成内容填写成实验结论。
5. 以 UTF-8 保存有效 JSON；大量导入时，外部整理脚本也只需生成同样的 `records` 数组。建议先备份，再用 `python -m json.tool data/materials/6A01/welding_cases.json` 检查语法。
6. 页面点击“重新读取材料数据”，核对数量、状态、方法和原始记录。读取不使用永久缓存，无需重建向量索引；主页面已有推荐保持原样，点击“生成焊接工艺推荐”后才更新。

空文件、缺失文件、顶层 null 均按空数据读取；非法 JSON 或结构不符会提示并跳过，不会自动覆盖原文件。完全空的模板和只有 id/alloy 的占位条目不计数；已填写的条目数不等于已审核样本数。指定状态、方法或厚度筛选时，未知字段不视为匹配，厚度采用精确匹配，不做邻近厚度外推。

### 统一查询接口与优先级

```python
from services.material_manager import MaterialManager

manager = MaterialManager()
manager.list_materials()
manager.get_material("6A01")
manager.get_tempers("6A01")
manager.get_welding_methods("6A01")
manager.get_welding_cases("6A01")
manager.get_properties("6A01")
manager.get_literature("6A01")
manager.get_summary("6A01")
manager.get_priority("6A01")  # ["6A01", "6xxx", "通用铝合金"]
# get_welding_cases 可选参数：temper、welding_method、thickness_mm。
# 传入真实条件即可筛选；不传条件则返回所有已填写记录。
```

推荐时先读取 6A01 专项档案、匹配的性能与案例及文献，再按 **6A01 → 6xxx → 通用铝合金** 排序本地知识；页面与解释上下文明确保留资料层级。6xxx 回退使用已有系列知识片段，不复制 6061 的具体参数或性能。只适用于其他牌号的知识片段不会作为 6A01 通用资料召回。

当前案例仅用于查询、原文展示和参考上下文，**不会自动转成工艺参数或模型训练数据**。6A01 工艺参数表保持为空，方法建议仍是基础规则初选；今后开放参数推荐需要单独建立来源、条件、审核与参数安全校验映射。未来预测继续预留 `agent/ml_interface.py` 的 `ProcessPredictionModel` 接口，专项页面如实显示“未训练 / 未接入”。

验证：`python -m pytest -q`。专项测试使用临时目录中的空值和路由元数据，不向材料库写入模拟实验；覆盖空库/缺失文件、字段空值、异常 JSON、即时重读、输入解析、优先级、原有材料及 Streamlit 跨页运行。

## LLM 调用架构升级

上层 Agent 统一调用 `services/llm/router.py` 中的 `LLMRouter`：联网 API → Ollama → 规则解释。
本次仅升级模型调用架构，保留原有知识库、推荐规则、解释提示词和数值安全校验，不训练模型。

1. 安装新增依赖：`python -m pip install -r requirements.txt`。
2. 编辑项目根目录 `.env`（缺失时可复制 `.env.example`），填写：

   ```dotenv
   LLM_PROVIDER=openai-compatible
   LLM_BASE_URL=
   LLM_API_KEY=
   LLM_MODEL=
   ```

   Base URL 填写服务商的 API 根地址，保留所需的 `/v1` 等路径前缀，不含 `/chat/completions`。
   模型名填写服务商提供且账号有权限调用的名称；Key 只放 `.env` 或进程环境变量。
   `.env` 已被 Git 忽略，程序不在页面展示 Key，也不记录请求头、提示词、响应正文和原始异常。
   协议采用 [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。
3. 在 `config/model_config.yaml` 设置 cloud / local 模型、连接与读取超时、fallback 策略。
   进程环境变量优先于 `.env`，非空环境配置优先于 YAML。API Key 不从 YAML 读取。
   `fallback.enabled: true` 配合 `strategy: cloud_then_local` 启用云端失败后转本地；关闭后云端失败直接用规则解释。
   `LLM_PROVIDER=ollama` 可显式指定仅调用本地。无论策略如何，两端不可用均显示“AI解释模块不可用”，继续规则推荐。
4. 启动 `streamlit run app.py`，进入侧栏“模型设置”，点击“重新加载配置”，再点击“测试连接”。
   页面重跑时也会自动应用配置变化；已经生成的结果会保留，需要再次点击“生成焊接工艺推荐”更新解释。
   测试使用简短中性提示词实际调用两端生成接口；会显示成功/失败、检查时间、响应时间和错误类型。
   “当前使用模型”表示本会话最近一次推荐调用的模型，连接测试不会覆盖它；首次调用前显示“尚未调用”。
   本地模型冷启动可适当增大 `timeout.test_seconds`。超时为连接/读取超时，不是端到端总时限。
   正式云端解释的读取超时为 180 秒。简短连接测试成功不代表完整解释能在相同时间内完成；深度思考模型可能需要几十秒。
5. 调用日志保存在 `logs/llm-calls-YYYY-MM.jsonl`，每次尝试分别记录模型、提供方、调用时间、操作、成功/失败、耗时和错误分类。

API 网络异常、Key/权限错误、限流、服务异常、无效响应或空文本均触发本地降级。下一次请求重新优先尝试云端。
原有 `config/settings.yaml` 的 ollama 段仅保留兼容读取，运行时请修改新的 `model_config.yaml`。

验证命令：

```powershell
python -m pytest -q
python scripts/check_llm.py
```

前者执行隔离的客户端、HTTP 协议、fallback、规则回归和页面测试，不需要外部模型。
后者读取真实配置并调用真实服务；任一服务不可用时退出码为 1。模拟测试通过不代表真实凭据或本地模型已可用。

这是一个面向 Windows 10/11、普通学生电脑和科研初选场景的可运行第一版。用户输入铝合金、状态、板厚、接头、位置和性能偏好后，系统按以下顺序工作：

```text
输入校验
  → 材料种子库
  → 基础规则引擎
  → 有条件匹配的工艺参数库
  → 本地知识库检索
  → LLM Router 中文解释（联网 API 优先，Ollama 备用，可选）
  → 参数安全检查
  → 页面展示、导出与本地日志
```

关键原则是：**关键参数不由大模型生成**。电流、电压、焊速、气体流量、温度等只有在结构化数据库命中适用条件且具备来源、可信度和示例标记时才会显示。没有可靠数据时，页面明确显示“数据不足 / 需要焊接工艺评定验证”。

> 本软件只用于学习、科研和焊接工艺初选，不替代正式 WPS/PQR、焊接工艺评定、产品标准、设计审查或持证焊接工程师判断。尤其不得把示例参数直接用于承载、安全关键或生产构件。

## 当前支持范围

- 材料：6061、6063、5083、5052、2024、7075。
- 状态：O、常用 H 状态、T3/T4、T6/T651；每个牌号在界面中只显示合理的候选状态。
- 方法：TIG/GTAW、MIG/GMAW、激光焊、搅拌摩擦焊 FSW。
- TIG/MIG：具备通用工艺要点、填丝初选和少量严格限定条件的厂商示例数据。
- 激光焊/FSW：当前主要用于方法筛选和知识检索，不提供设备相关的精确参数。
- RAG：PDF、TXT、Markdown；保留文件名、片段和可抽取的 PDF 页码。
- 导出：Markdown 和 JSON。
- 降级：联网 API 失败后自动切换 Ollama；两端都不可用时，规则、数据库、RAG、日志和导出仍可使用。

## 项目结构

```text
.
├── app.py                         # Streamlit 中文界面
├── requirements.txt
├── config/
│   ├── settings.yaml              # RAG和应用配置
│   └── model_config.yaml          # 云端、本地模型、超时和fallback策略
├── agent/
│   ├── input_normalizer.py        # 输入规范化与校验
│   ├── models.py                  # 请求/结果数据结构
│   ├── rule_engine.py             # 方法筛选规则
│   ├── safety_checker.py          # 参数与LLM解释安全检查
│   ├── recommender.py             # 完整推荐流水线
│   └── ml_interface.py            # 未来预测模型接口
├── data/
│   ├── materials/materials.json   # 材料与填丝种子库
│   ├── processes/process_parameters.json
│   └── welding_cases/             # 未来试焊/PQR案例
├── knowledge/source_docs/         # 待检索PDF/TXT/Markdown
├── vector_db/                     # 生成的本地哈希向量索引
├── scripts/import_knowledge.py
├── services/                       # 数据、RAG、日志、导出
│   └── llm/                      # base / api_client / ollama_client / router
├── pages/1_模型设置.py             # 模型与服务状态、连接测试
├── utils/
├── logs/                           # 本地JSONL推荐日志
└── tests/
```

## 一、Windows 新手安装

### 1. 安装 Python

推荐 **64 位 Python 3.11 或 3.12**。本项目已用 Python 3.12 测试。进入 [Python 官方 Windows 下载页](https://www.python.org/downloads/windows/) 下载 64 位安装程序。

安装第一屏务必勾选：

- `Add python.exe to PATH`
- `Install launcher for all users`（若界面提供）

安装后重新打开 PowerShell，检查：

```powershell
python --version
```

若 `python` 不可用但 `py` 可用，可把后续命令中的 `python` 换成 `py -3.12`。

### 2. 打开项目并创建虚拟环境

在资源管理器打开项目目录，点击地址栏输入 `powershell` 并回车。然后执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

提示符前出现 `(.venv)` 表示激活成功。如果 PowerShell 提示禁止运行脚本，只为当前窗口临时放行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

也可以完全不激活，后续直接使用 `.venv\Scripts\python.exe`。

### 3. 安装 Python 依赖

联网安装一次：

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

安装后验证：

```powershell
python -m pytest -q
```

预期全部测试通过。

## 二、安装和配置 Ollama

### 1. 安装 Ollama

从 [Ollama 官方 Windows 下载页](https://ollama.com/download/windows) 安装。安装程序一般会启动后台服务；系统托盘可以看到 Ollama 图标。

PowerShell 检查：

```powershell
ollama --version
ollama list
```

### 2. 下载默认中文模型

16GB 内存电脑优先使用约 7B 的 Q4 量化模型：

```powershell
ollama pull qwen2.5:7b-instruct-q4_K_M
```

内存不足、纯 CPU 响应太慢或同时还要运行其他软件时，改用更小模型：

```powershell
ollama pull qwen2.5:3b-instruct-q4_K_M
```

然后编辑 [config/model_config.yaml](config/model_config.yaml) 中的 local 段，把：

```yaml
model: "qwen2.5:7b-instruct-q4_K_M"
```

改成：

```yaml
model: "qwen2.5:3b-instruct-q4_K_M"
```

模型标签必须与 `ollama list` 第一列完全一致。如果某个量化标签在你的 Ollama 版本/仓库中不存在，可先执行 `ollama pull qwen2.5:7b`，再把配置改为 `qwen2.5:7b`。

### 3. 启动 Ollama

Windows 安装版通常自动启动。若没有启动：

```powershell
ollama serve
```

这个窗口需要保持打开。另开一个 PowerShell 执行：

```powershell
ollama list
```

默认本地地址为 `http://127.0.0.1:11434`。需要完全离线时，在 `.env` 中设置 `LLM_PROVIDER=ollama`。

## 三、启动应用

激活虚拟环境后，在项目根目录执行：

```powershell
streamlit run app.py
```

如果没有激活环境：

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

浏览器一般自动打开 `http://localhost:8501`。没有自动打开时，把该地址复制到浏览器。

建议首次验收输入：

- 材料：6061 / T6
- 板厚：3 mm
- 接头：对接
- 位置：平焊
- 方法：自动推荐
- 要求：较高强度、低变形、关注裂纹

这个对接场景会读取材料库、TIG 通用数据库条目和填丝候选，但不会错误套用只适用于角焊缝的精确电流表。把接头改为 `T形接头`，才会命中种子库中明确限定为约 3.2 mm 平位置角焊缝的厂商示例范围。两种情况都必须做试焊和 WPS/PQR。

## 四、导入本地知识库

把资料复制到：

```text
knowledge\source_docs\
```

支持扩展名：

- `.pdf`
- `.txt`
- `.md`

然后在项目根目录执行：

```powershell
python scripts\import_knowledge.py
```

成功后会生成：

```text
vector_db\knowledge_index.json
```

当前采用**确定性字符 n-gram 哈希嵌入**：完全本地、不下载 embedding 模型、资源占用低，适合小型知识库和中文关键词/术语检索。数据量变大或需要更强语义检索时，可以保持 `RagService.search()` 接口不变，内部替换成 FAISS/Chroma 加本地 embedding 模型。

PDF 页码按 PDF 内部页面顺序保存。扫描图片型 PDF 没有文本层时，`pypdf` 无法抽取内容；请先使用离线 OCR 软件生成可搜索 PDF。导入受版权保护的标准、论文或手册前，请确认你拥有合法使用权限；不要把私人资料提交到公共仓库。

## 五、增加或修改材料数据

材料文件是 `data/materials/materials.json`。每种材料至少包含：

```json
{
  "alloy": "示例牌号",
  "supported_tempers": ["O", "T6"],
  "series": "6xxx",
  "alloy_system": "合金体系",
  "strengthening": "强化机制",
  "weldability": "有来源支持的定性结论",
  "fusion_risk_level": "低/中/高",
  "primary_risks": ["风险1", "风险2"],
  "source_ids": ["来源ID"],
  "filler_options": []
}
```

同时在文件顶部 `sources` 中定义来源标题、URL 和用途。不要把个人经验写成“高可信度”。如果只有内部实验报告，可把 URL 留空，但应在 `note` 写明报告编号、版本、日期、审核人和保存位置。

增加新牌号后还需要：

1. 在 `agent/models.py` 的 `SUPPORTED_ALLOYS` 增加牌号。
2. 在 `app.py` 的 `temper_options` 增加状态选项。
3. 按需要调整 `agent/rule_engine.py` 的规则。
4. 增加测试，再执行 `python -m pytest -q`。

## 六、增加工艺参数数据

工艺文件是 `data/processes/process_parameters.json`。每条记录必须限定方法、合金、接头、位置和厚度窗口。每个参数必须包含：

```json
{
  "name": "电流范围",
  "value": {"min": 100, "max": 120},
  "unit": "A",
  "source_id": "唯一来源ID",
  "confidence": "高/中/低",
  "example_data": true,
  "note": "设备、焊丝、位置及任何不能外推的条件"
}
```

重要规则：

- `value` 的范围和单位必须忠实于来源；换算时在 `note` 保留原单位和换算方法。
- `applicable_conditions` 必须足够具体，不能只写“铝合金适用”。
- 厂商推荐起点和论文单组试验值通常应标记 `example_data: true`。
- 来自已批准 WPS/PQR 的数据也只能用于其覆盖范围，不能自动外推。
- 没有可靠数值就写 `null`。安全检查会拦截空数值，但页面仍会显示数据不足提示。
- 两条同等具体度记录若给出不同值，系统会显示冲突，不会静默合并。

建议后续按这个优先级补充：适用的国家/行业/产品标准 → 经批准的单位 WPS/PQR → 权威焊接手册 → 设备/焊材制造商数据 → 同条件同行评议论文 → 已审核实验数据。标准常受版权保护，建议保存允许使用的摘要和定位信息，不要未经许可复制全文。

## 七、参数安全机制

第一版采用多层隔离：

1. LLM 不参与规则评分和数据库筛选。
2. 给 Ollama 的解释上下文只包含参数名称，不包含结构化数值表。
3. 页面参数区只读取结构化数据库。
4. 每个参数必须具备来源 ID、可信度和适用条件，否则被拦截。
5. 数值参数为 `null` 时不显示虚构范围。
6. LLM 解释若出现带 A、V、Hz、转速、速度、流量或温度单位的新数值，整段解释会被舍弃并回退到确定性规则文本。
7. 2024、7075 被标记为传统熔焊高风险；自动推荐优先评估 FSW，显式选择 TIG/MIG 时也不会得到普通铝合金参数。
8. 不同知识文件若对同类关键参数出现不同数值，会显示“潜在冲突”并要求人工核对适用条件；系统不会自动选择看似更精确的一条。

这种机制不能代替人工审查，但可以避免把模型语言误当成可执行工艺卡。

## 八、电脑没有 NVIDIA 显卡怎么办

可以运行。Ollama 会用 CPU 和系统内存推理，规则、数据库和 RAG 本身对硬件要求很低。纯 CPU 下模型解释可能需要几十秒到几分钟，取决于处理器和上下文长度。

可按以下方式减轻负担：

- 在页面取消勾选“使用 Ollama 生成解释”，立即使用规则解释。
- 把模型改为 `qwen2.5:3b-instruct-q4_K_M`。
- 关闭占内存较多的软件。
- 不要一次导入大量超长 PDF；分批整理并删除无关文档。

没有 NVIDIA 显卡不会影响参数安全逻辑，也不会阻止应用启动。

## 九、16GB RAM 和硬件建议

最低目标：

- Windows 10/11 64位
- 16GB RAM
- 50GB 可用 SSD
- 无独显可运行，模型解释较慢

16GB RAM 建议：

- 首选 7B 左右 Q4 量化模型；如果系统可用内存不足或频繁换页，使用 3B Q4。
- 不建议同时加载多个大模型。
- 保持 Ollama 上下文和输出简洁；本项目已经只发送少量检索片段。

推荐配置：16–32GB RAM，RTX 3060 12GB 或更高。项目不假设存在高端 GPU。

## 十、如何彻底离线运行

规则推荐不需要互联网。设置 `LLM_PROVIDER=ollama` 后，解释也仅调用本地模型。第一次准备依赖和模型可在联网机器完成，然后复制到离线电脑。

### Python 依赖离线包

在一台与离线电脑同为 Windows 64位、Python 大版本相同的联网电脑上：

```powershell
python -m pip download -r requirements.txt -d wheels
```

把整个项目和 `wheels` 目录复制到离线电脑，然后：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --no-index --find-links .\wheels -r requirements.txt
```

### Ollama 模型离线迁移

在联网 Windows 电脑安装同版本 Ollama 并完成 `ollama pull`。退出 Ollama 后，复制整个模型目录：

```text
%USERPROFILE%\.ollama\models
```

到离线电脑的相同位置，再启动 Ollama 并执行 `ollama list` 验证。也可以使用 Ollama 官方支持的 `OLLAMA_MODELS` 环境变量指定一个容量足够的本地目录；迁移前后应保持目录结构不变。

### 网络隔离核对

- `config/settings.yaml` 中 Ollama 地址保持 `http://127.0.0.1:11434`。
- 运行时不要执行 `pip install`、`ollama pull` 或打开外部来源链接。
- 来源 URL 仅用于追溯展示，应用不会自动抓取这些网页。
- 知识库索引和推荐日志都保存在项目本地。
- 如有严格保密要求，可用 Windows 防火墙禁止 Python、Streamlit 和 Ollama 出站，再执行全部测试。

## 十一、常见错误

### `python` 不是可识别的命令

重新安装 Python 并勾选 Add Python to PATH，或尝试：

```powershell
py -3.12 --version
```

### 无法运行 `Activate.ps1`

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

这只影响当前 PowerShell 窗口。

### `streamlit` 不是可识别的命令

虚拟环境没有激活，或依赖装到了另一个 Python。使用：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

### Ollama 未连接

确认系统托盘中的 Ollama 正在运行，或执行 `ollama serve`。再检查：

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Ollama 不可用不会使基础推荐失败。

### 目标模型未安装

执行 `ollama pull <模型名>`，并确保 `config/model_config.yaml` 的 local.model 与 `ollama list` 完全一致。

### 端口 8501 被占用

```powershell
streamlit run app.py --server.port 8502
```

### PDF 导入后检索不到

先确认 PDF 是否可以选中文字。扫描件需要离线 OCR。重新执行 `python scripts\import_knowledge.py`，并查看输出的文件数和片段数。

### 中文路径显示乱码

项目代码和数据全部使用 UTF-8。旧版控制台可能只影响终端显示，不影响文件内容。可执行：

```powershell
chcp 65001
```

或使用 Windows Terminal / PowerShell 7。

### 内存不足或模型非常慢

关闭 Ollama 中的大模型，改用 3B Q4，并在页面临时关闭 LLM。规则推荐和本地哈希 RAG不需要加载大模型。

### 知识来源冲突

不要手动删掉警告。先比较材料状态、接头、位置、厚度、设备波形和单位是否一致；无法确认时保留两条记录并降低可信度，由焊接工程师决定采用哪一来源。

## 十二、测试与开发检查

执行全部测试：

```powershell
python -m pytest -q
```

执行语法编译检查：

```powershell
python -m compileall -q app.py agent services utils scripts tests
```

重建知识库：

```powershell
python scripts\import_knowledge.py
```

测试覆盖输入范围、种子数据、6061 验收场景、限定条件数值匹配、7075 高风险行为、参数拦截、本地 RAG 来源信息和 Streamlit 页面启动。

## 十三、种子数据来源与边界

当前种子库引用以下公开技术资料，并在每个数据项上保存来源 ID：

- [TWI：Aluminium alloys weldability](https://www.twi-global.com/technical-knowledge/job-knowledge/weldability-of-materials-aluminium-alloys-021)
- [ESAB：2024 and 7075 welding risk](https://esab.com/us/nam_en/esab-university/blogs/how-do-i-weld-2024-and-7075/)
- [ESAB：Aluminium filler metal selection](https://esab.com/ad/eur_en/esab-university/articles/choosing-filler-metal-for-aluminium-welding/)
- [Miller：Industrial aluminum welding basics](https://www.millerwelds.com/en-us/resources/knowledge-hub/aluminum-welding/guide-to-industrial-aluminum-welding)
- [Miller：Aluminum welding guide, TIG example table](https://www.millerwelds.com/-/media/miller-electric/files/pdf/resources/aluminum_welding_guide.pdf)
- [Lincoln Electric：Aluminum GMAW table 6-3](https://ch-delivery.lincolnelectric.com/api/public/content/3353e67959b74173b336498aface1f3f?v=d5d4eabf)

厂商表中的少量数值只在数据库明确限定的厚度、接头和位置条件下出现，并标为“示例数据”。种子库不是完整标准数据库，也没有覆盖材料批次、设备波形、坡口尺寸、装配间隙、环境和全部检测要求。

## 十四、科研数据管理框架（当前阶段）

新增侧边栏 **科研数据管理**：支持 CSV、Excel（XLSX/XLS）、JSON 导入，17 个核心实验字段、单位校验、缺失/重复/异常检查、SQLite 事务版本管理，以及数据量、字段完整度、材料/焊接方法分布和历史版本查看。

详见 [data_manager 使用说明](data_manager/README.md)。默认仓库位于 `data/research/`；正式记录和 Demo 测试占位记录分开。空白模板可在页面下载。不会自动导入旧草稿，不训练模型、不预测、不优化，不生成实验测量数据。

实际 Demo 导入命令：

```powershell
.\.venv\Scripts\python.exe scripts\import_dataset.py data\templates\demo_schema_only.csv --dataset demo
```

Demo 只有一条无测量值的结构测试记录，重复导入会被拦截。检查而不写入时增加 `--dry-run`；完整验收结果见 [DATA_MANAGER_TEST_REPORT.md](DATA_MANAGER_TEST_REPORT.md)。

## 十五、机器学习预测模块框架

新增 `modeling/` 和侧边栏 **模型管理**。统一支持未来 Random Forest、XGBoost、Gaussian Process、MLP 的训练、保存、评价和预测接口；记录模型版本、特征、目标、训练时间、数据版本与指标。

**本阶段不训练真实模型，不生成虚假实验数据。** 训练入口默认关闭，页面训练按钮禁用。没有模型时显示“暂无训练模型”；`from agent.ml_interface import predict; predict({})` 返回 `no_model`，预测性能为空、置信度不可用。模型预测暂不自动并入现有工艺推荐结果。

详细说明及未来接入方式见 [modeling/README.md](modeling/README.md)。可选训练依赖单独列在 `requirements-modeling.txt`，当前空数据运行无需安装。

空数据验收与回归测试结果见 [MODELING_TEST_REPORT.md](MODELING_TEST_REPORT.md)：新增 37 项专项测试，全项目 175 项测试通过。

## 十六、后续扩展建议

保持第一版稳定后，再按真实研究需求逐步增加：

1. 用单位已批准的 WPS/PQR 和实验数据扩充精确条件记录。
2. 给数据增加版本、审核状态、有效期和适用标准版本。
3. 用本地中文 embedding + FAISS/Chroma 替换哈希检索。
4. 增加 OCR 管道和文档重复/冲突检测。
5. 收集经核验的真实实验数据后，启用 `modeling/train.py` 并校准不确定性；再将预测结果与数据库参数分区展示。
6. 增加用户角色、项目号、审核签名和不可篡改导出报告。
