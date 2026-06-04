"""将 data/ 目录下所有 txt 资料文件导入 PGVector 知识库。每个文件只需导入一次。"""
import os
from src.rag_function import import_knowledge_file, list_imported_files

data_dir = os.path.join(os.path.dirname(__file__), "data")
data_dir = os.path.abspath(data_dir)

if not os.path.isdir(data_dir):
    print("data/ 目录不存在")
    exit(1)

imported = set(list_imported_files())

for fname in sorted(os.listdir(data_dir)):
    if not fname.endswith(".txt"):
        continue
    fpath = os.path.join(data_dir, fname)
    size_kb = round(os.path.getsize(fpath) / 1024, 1)

    if fname in imported:
        print(f"⏭️  {fname} ({size_kb} KB) — 已导入，跳过")
        continue

    print(f"📥 正在导入 {fname} ({size_kb} KB) …", end=" ", flush=True)
    try:
        result = import_knowledge_file(fname)
        print(f"✅ {result}")
    except Exception as e:
        print(f"❌ 失败: {e}")
