# 本地知识索引

运行 `python scripts/import_knowledge.py` 后会在本目录生成 `knowledge_index.json`。索引使用完全离线的确定性字符 n-gram 哈希嵌入，不下载模型，适合小型种子库和 16GB 内存电脑。未来数据量显著增加时，可在不改推荐流程接口的前提下替换为 FAISS/Chroma 与本地语义 embedding 模型。

