# 科研数据管理框架

本模块仅处理科研数据导入、Schema、质量检查、版本和浏览，不调用 Agent、LLM、训练、预测或优化接口。不会补齐测量、计算热输入或从论文自动编造实验行。原材料库和 `data/imports/6A01_welding_demo_dataset/` 草稿不自动迁移。

## 快速使用

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

打开侧边栏 **科研数据管理**，选择正式科研数据或 Demo 仓库，上传文件，检查报告与标准化预览后点击“导入并创建版本”。数据量、字段完整度、材料分布、焊接方法分布随仓库及历史版本切换。记录按 100 条分页，支持材料和方法筛选。

命令行检查与导入：

```powershell
.\.venv\Scripts\python.exe scripts\import_dataset.py data\templates\demo_schema_only.csv --dataset demo --dry-run
.\.venv\Scripts\python.exe scripts\import_dataset.py data\templates\demo_schema_only.csv --dataset demo
```

重复执行导入会返回退出码 2 并阻止重复入库。`--dry-run` 只读；成功退出码 0，校验或格式错误退出码 2。`--root` 可指定独立仓库目录；`--sheet` 选择 Excel 工作表；`--encoding gb18030` 支持中文旧编码 CSV。

## Schema 1.0.0

`schema.py` 是字段定义的唯一维护来源。`experiment.schema.json` 是标准化记录的 JSON Schema，可通过页面下载。外部输入允许省略可选字段，标准化输出包含全部 17 个核心字段及 `record_kind`；未知字段会报错，避免静默丢列。

| 分组 | 字段 | 标准格式 / 单位 |
|---|---|---|
| 材料 | alloy / temper / thickness | 文本 / 文本 / mm |
| 焊接 | process / current / voltage / speed / heat_input | 文本 / A / V / mm/s / kJ/mm |
| 性能 | tensile_strength / hardness / elongation | MPa / HV / % |
| 缺陷 | porosity / crack / undercut | 气孔率 % / present、absent、unknown / 咬边深度 mm |
| 来源 | paper / experiment_id / source | 论文标识或引文 / 来源内唯一实验编号 / 来源标识 |

`alloy`、`experiment_id`、`source` 必填；其他字段允许为空并产生缺失提示。`source` 应使用稳定来源标识（如 DOI、原始实验台账编号），`experiment_id` 应标识独立记录；Excel 中编号须设为文本，以保留前导零。同论文的不同实验必须使用不同编号。

`record_kind` 默认 `experimental`，表示导入者声明的实验记录，并非系统核实结论；Demo 必须填写 `schema_test`。正式仓库拒收 `schema_test`；Demo 仓库拒收 `experimental`。框架无法识别被人为错误标注的测试记录，导入者应如实提供来源和记录性质。

空白、NA、N/A、null、None、NaN、未知、待补充、未提供作为缺失标记。**0 是数据，不能当缺失值**。`crack=unknown` 为显式“未知”标签；完整度按字段有无填写统计，不代表缺陷已测定。统计分母包含全部 17 个核心字段，未按方法排除不适用字段，因此 FSW 的电流空缺也会计入缺失提示。

## 单位与文件格式

数值单位可用以下任一方式声明。多处声明必须一致，冲突时不擅自选取：

- CSV / Excel 列名：`thickness[mm]`、`speed[mm/min]`。
- 独立单位列：`thickness` 与 `thickness_unit`。
- 单元格后缀：数值后接 `mm` 等明确单位。
- JSON 数值对象：`{"value": null, "unit": "mm"}`。
- JSON 顶层：`{"records": [], "units": {"thickness": "mm"}}`。

JSON 也支持直接记录数组。CSV 支持逗号分隔及标准引号转义，默认 UTF-8（含 BOM）。Excel 支持 `.xlsx` / `.xls`，默认读取第一张工作表，可按名称指定；表头必须位于第一行。XLSX 公式不作为原始值导入；旧 XLS 读取文件中的缓存值，xlrd 无法区分这些值是否来自公式，使用 XLS 时应先核对原始数值。日期、布尔数值及错误单元格不作为测量导入。非标准列名需先显式映射，框架不会猜测旧表字段含义。

无单位数值默认报错。只有导入者明确勾选页面声明或指定 `--assume-canonical-units`，才按标准单位解释，并写入版本元数据和检查报告。系统无法仅凭一个看似合理的数值发现来源标注错误。

支持 cm/m/µm→mm，kA/mA→A，kV/mV→V，mm/min、m/min、m/s→mm/s，J/mm、kJ/cm、J/cm→kJ/mm，GPa/Pa/N/mm²→MPa，以及 fraction→百分数。保留原文件，标准化值单独入库。

硬度只接受 HV，不把 HB/HRC 或载荷信息擅自换算成 HV；气孔的定性描述不转成百分数；咬边字段定义为深度，不混用布尔标签。热输入只读来源值，不根据电流、电压、速度计算。

## 数据检查和提交规则

| 检查 | 行为 |
|---|---|
| 必填字段缺失、类型错误、未知列、无效/冲突单位 | 阻止整批入库 |
| 负测量值、非有限数值、气孔率超出 0–100%、严格正值字段为 0 | 阻止整批入库 |
| source + experiment_id 重复、完整记录重复 | 检查本批与当前仓库全部历史记录；阻止整批入库 |
| 相同材料/状态/方法及测量值、但来源或实验编号不同 | 标记疑似重复，保留可能的平行实验，不自动删除 |
| 可选字段缺失 | 按字段报告缺失数，保留 null |
| 统计异常值 | 同材料/状态/方法分组，每个数值字段至少 8 个观测时，用 3×IQR 标记新记录；不删除、不修正 |

严格正值字段为 thickness、speed、tensile_strength、hardness；其他数值字段允许 0。伸长率不设 100% 上限。以上规则是数据格式和复核规则，不是焊接工艺许可范围。统计分组没有包含全部实验条件，异常提示需要结合厚度、接头等原始信息人工复核；样本不足时不执行统计异常检测。

错误一旦存在，**整批不提交**，也不产生新版本；不会偷偷只导入“好行”。详情最多保留 2000 项，同时完整保存错误、警告和各字段缺失计数。可修正原文件后重新检查；页面预览后点击导入时会在写事务中再次检查重复数据。

## 数据版本与存储

默认存储：`data/research/datasets.sqlite3`。同一数据库下 `research` 和 `demo` 为独立逻辑仓库，各自从 `v000001` 递增。每次成功导入保存：

- dataset_version、parent_version、schema_version；
- updated_at（UTC ISO 8601）；record_count（累计）、added_count（新增）；
- 原文件名、SHA-256、Excel 工作表、编码、单位声明选项；
- 原文件完整字节和质量报告；每条标准化记录的版本和原始行号。

采用 SQLite 事务和唯一约束，版本元数据、原文件和记录同时成功或回滚；并发写入串行化。同一仓库的历史视图由 `导入版本 <= 所选版本` 重建，无需每次复制全量快照。只提供追加与历史读取，不提供覆盖、删除或同 ID 修订操作。历史记录只读保护由 API 保证；数据库文件不是防篡改审计系统。

备份时先停止应用，再复制整个 `data/research/` 目录（含可能存在的 WAL/SHM），或使用 SQLite 在线备份接口。不要在运行时只拷贝主数据库文件。

统计通过 SQL 聚合、列表分页；已有记录以游标读取，不每次复制全部历史记录到 Python 字典列表。当前上传文件和待导入批次仍在内存中，重复检查保存键集合，统计异常保存相关组的数值；适合先按批次导入。页面遵循 Streamlit 上传大小限制（通常默认 200 MB）。百万级以上数据应再增加流式解析、后台导入任务和定向去重索引，并在目标机器上做容量验证；本阶段只验收 10,000 条无测量占位记录的批量路径，不宣称完成百万级性能测试。

## Python 接口

```python
from data_manager import DataManager

manager = DataManager()
report = manager.preview_bytes(content, filename, dataset="research")
if report.ok:
    version = manager.import_bytes(content, filename, dataset="research")
history = manager.versions("research")
summary = manager.summary("research")
rows = manager.records("research", limit=100, offset=0)
old_summary = manager.summary("research", version=1)
```

所有默认读取均为正式仓库。Demo 必须显式选择 `dataset="demo"`。导入模块不写 `data/materials/`，不接入现有推荐、RAG 或模型接口。

## Demo 边界

`data/templates/demo_schema_only.csv` 只有一条路由测试占位记录：6A01、测试编号、`demo_placeholder_no_measurements` 来源标记及 `schema_test`。未填写状态、焊接方法、任何焊接参数、性能或缺陷。它不是实验数据；正式科研数据量保持 0。测试中的数值仅为临时目录内的单位算术和错误边界输入，不保存到交付的科研仓库。
