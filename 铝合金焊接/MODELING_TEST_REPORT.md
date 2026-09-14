# 机器学习预测框架验收

日期：2026-09-13

## 实现范围

- 新增 modeling/dataset.py、feature_engineering.py、train.py、predict.py、evaluate.py、registry.py。
- backends.py 提供 Random Forest、XGBoost、Gaussian Process、MLP 的统一 fit / predict / uncertainty 适配器，机器学习依赖按需导入。
- agent/ml_interface.py 暴露 predict(welding_parameters) 与 WeldingPredictor；主页增加「模型管理」入口。
- 模型注册记录版本、特征、目标、训练状态、时间和耗时、数据版本及摘要、指标、划分记录和依赖版本。
- 页面展示模型清单、状态、指标和数据可用性；训练按钮禁用。训练函数默认 enable_training=False。
- 无模型返回 no_model、空 predicted_performance 和不可用 confidence，不生成占位预测或百分比。

## 测试结果

| 检查 | 结果 |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/test_modeling.py -q` | 37 passed，1.68 秒 |
| `.venv/Scripts/python.exe -m pytest -q` | 175 passed，289.19 秒 |
| compileall：modeling、agent/ml_interface.py、模型管理页面 | 通过 |
| 实际正式仓库记录数 | 0 |
| 实际 Demo 记录数 | 1，原有无测量值占位记录 |
| 实际模型清单 | [] |
| data/models 目录 | 未创建 |
| 实际 predict({}) | no_model；“暂无训练模型”；预测值为空，置信度不可用 |
| 实际四类模型 train() | 全部 no_data，无模型构造、训练或保存 |

专项测试覆盖：无仓库、Demo 隔离、固定数据版本、非实验记录与缺失目标剔除、默认训练关闭、
特征泄漏拦截、输入无效/缺失、空评价与不可定义 R²、注册状态及保存回读、摘要校验、
路径限制、失败版本排除、损坏元数据、缺失模型文件、预测协议及超出训练范围拒绝、
Streamlit 空页面导航、四类算法切换、训练按钮禁用，以及已有版本状态/指标展示。

最初一项页面测试直接以子页面作为入口，导致 Streamlit 无法解析同级页面链接；
测试已改为从 app.py 按实际导航进入，专项及全量回归均通过。

## 数据与训练边界

科研数据库 `data/research/datasets.sqlite3` 测试前后 SHA-256 均为：

`A9B389C280658A833917AE785C09D71287CA644A38D932BD25B5F3C9B4E8FB82`

未执行真实 estimator.fit，未生成实验数据，未写入正式模型目录。
测试中的数值仅用于确定性指标算术和预测协议 mock；序列化对象仅为临时测试哨兵，
不属于训练模型或实验记录，不导入科研仓库、不展示于实际模型管理页。

当前环境未安装 scikit-learn / XGBoost；本次确认在缺少这些可选依赖时空数据流程正常。
四类真实模型的训练效果、完整训练往返及不确定性校准未测试，留待有真实数据且明确启用训练后验收。
GP 标准差只是模型假设下的不确定性，其他模型暂返回不可用；所有模型均不提供未经校准的置信百分比。

使用说明见 [modeling/README.md](modeling/README.md)。
