# 科研数据仓库

`datasets.sqlite3` 由 `data_manager.DataManager` 管理，保存标准化记录、版本元数据、原始导入文件及检查报告。正式数据 `research` 与测试数据 `demo` 独立计数、独立版本。

当前仅完成一条 `schema_test` 占位 CSV 的实际导入；所有焊接、性能和缺陷测量为空。正式科研数据为 0。

`demo_import_verification.json` 为本次实际验收快照，不是持续自动刷新的统计文件。最新统计请在“科研数据管理”页面查看。

备份时停止应用后复制整个目录（包括可能存在的 WAL/SHM），或使用 SQLite 在线备份接口。使用与字段说明见 `../../data_manager/README.md`。
