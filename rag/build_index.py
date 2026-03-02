import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# تحميل النصوص
with open("chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

# موديل embeddings (قوي للعربي)
model = SentenceTransformer("intfloat/multilingual-e5-base")

embeddings = model.encode(chunks)

dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(np.array(embeddings))

faiss.write_index(index, "index.faiss")

print("تم بناء قاعدة البحث ✅")