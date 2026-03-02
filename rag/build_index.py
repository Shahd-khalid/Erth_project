import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# تحميل النصوص
with open("rag/chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

# موديل embeddings (استخدمت الإصدار الصغير small لسرعة التشغيل على Render)
model = SentenceTransformer("intfloat/multilingual-e5-small")

embeddings = model.encode(chunks)

dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(np.array(embeddings))

faiss.write_index(index, "rag/index.faiss")

print("تم بناء قاعدة البحث ✅")