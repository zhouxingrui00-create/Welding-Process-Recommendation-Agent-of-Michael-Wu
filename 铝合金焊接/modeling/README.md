# 机器学习预测框架

本阶段只建立框架，不执行真实训练、不生成或导入虚假实验数据。
首页侧边栏新增「模型管理」；与「模型设置」中的 LLM 连接配置独立。
空仓库显示 **暂无训练模型**，不创建占位模型或伪造评价指标。

## 组成

| 文件 | 职责 |
| --- | --- |
| dataset.py | 固定 research 数据版本、读取完整实验记录、记录剔除原因与内容 SHA-256 |
| feature_engineering.py | 统一特征顺序、类型/范围检查、类别编码、标准化、训练范围检查 |
| backends.py | fit / predict / uncertainty 统一协议与四类回归器的延迟加载适配 |
| train.py | 默认关闭的训练入口、按来源划分留出集、评价和版本保存 |
| predict.py | 函数和对象形式的 Agent 预测入口 |
| evaluate.py | MAE、RMSE、R²；空数据和不可定义指标返回 None |
| registry.py | 训练状态、模型文件、版本元数据、原子写入与文件摘要校验 |

支持算法 ID：`random_forest`、`xgboost`、`gaussian_process`、`mlp`。
核心应用不依赖 scikit-learn / XGBoost；未来实际训练或加载模型前再安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-modeling.txt
```

## 数据与接口

默认输入：alloy、temper、process、thickness、current、voltage、speed、heat_input。
可显式选择子集以适配不同工艺。单位与科研数据 Schema 一致：mm、A、V、mm/s、kJ/mm。
预测入口接收标准单位的数值，不自动转换单位、不计算热输入、不填补未知值。
target 可为 tensile_strength（MPa）、hardness（HV）、elongation（%），每个模型版本一个目标。
来源、缺陷及任何性能字段均不能作为输入，避免标签泄漏。
数据只读正式 research 快照并要求 record_kind=experimental；Demo 不进入训练。
缺失/无效目标和特征的行被剔除并计数，实验记录保持原样。

```python
from agent.ml_interface import predict, WeldingPredictor

# 空模型检查，不包含或生成任何实验数值。
result = predict({})
assert result["status"] == "no_model"
assert result["predicted_performance"] == {}
assert result["confidence"]["value"] is None

# 未来传入实际参数：predict(welding_parameters, target="hardness")
# 也可通过 WeldingPredictor(target="hardness").predict(welding_parameters) 调用。
```

成功响应包括 status、model_version、target、data_version、predicted_performance 和 confidence。
predicted_performance 按 target 返回 value 和 unit。
confidence 保留 value=None：不将模型误差、R²或树间差异冒充置信百分比。
GP 可返回后验 standard_deviation（目标单位），其余三类返回 available=False 和原因。
GP 标准差依赖模型假设，尚未做独立覆盖率校准。
缺失特征返回 invalid_input；超出训练范围/未知类别返回 out_of_domain 且无预测数值；
文件缺失、摘要错误、依赖缺失或推理失败返回 model_unavailable。
不指定 model_version 时选该 target 最新创建且训练完成的版本；这不代表它是最优模型。

## 未来训练入口（本次不执行）

`train()` 默认只读取与检查数据，空数据返回 no_data，有数据返回 disabled。
未来准备好正式实测数据后，可显式调用
`train(algorithm=..., target=..., feature_list=..., version=..., enable_training=True)`。
版本必须是正式仓库的整数版本号；省略时固定本次读取开始时的最新版本。
至少需要 2 个论文/来源分组，且划分后训练集、测试集各不少于 2 条；这只是运行下限，
不代表数据量足以获得可靠科研模型。默认固定随机种子 42、测试组比例 0.2。
相同 paper（无 paper 时用 source）的记录不跨组，来源标识须由数据维护者统一。
预处理只在训练分区 fit，测试数据只用于评价；不在评价后重拟合全部数据。

## 模型注册

运行目录为 `data/models/<model_version>/`，空状态不创建目录。
`model.pkl` 保存适配器及已拟合的完整预处理 pipeline；`metadata.json` 保存：

- model_version、algorithm、feature_list、target、feature_schema_version；
- status（training / trained / failed）、created_at、trained_at、training_duration_seconds；
- data_version、data_sha256、数据可用性摘要、参数、random_state；
- metrics（MAE / RMSE / R² / 留出样本数）、训练/测试记录标识与划分方法；
- feature_domain、依赖版本、模型文件名及 SHA-256、失败原因。

每次训练创建新版本；先写文件再发布 trained 元数据，失败版本不用于预测。
异常退出可能保留 training 状态，页面明确提示需核查；当前不包含后台调度、取消/恢复或自动训练。
pickle 仅适用于受信任的本地模型目录，不支持导入未知来源模型；摘要校验不是安全签名。
未来加载模型应使用元数据记录的相同依赖版本；跨版本兼容性不保证。

API 依据：[scikit-learn OneHotEncoder](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html)、
[GaussianProcessRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.gaussian_process.GaussianProcessRegressor.html)、
[XGBoost sklearn 接口](https://xgboost.readthedocs.io/en/stable/python/sklearn_estimator.html)。
