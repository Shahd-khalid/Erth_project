import os
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from groq import Groq

def test_rag():
    try:
        print("1. Loading Model...")
        model = SentenceTransformer("intfloat/multilingual-e5-small")
        
        print("2. Loading Index...")
        index = faiss.read_index("rag/index.faiss")
        
        print("3. Loading Chunks...")
        with open("rag/chunks.json", "r", encoding="utf-8") as f:
            chunks = json.load(f)
            
        print("4. Testing Encoding...")
        question = "كم نصيب الأم؟"
        question_embedding = model.encode([question]).astype('float32')
        
        print("5. Testing FAISS Search...")
        D, I = index.search(question_embedding, k=3)
        
        context = ""
        for i in I[0]:
            if i != -1:
                context += chunks[i] + "\n"
        print(f"   Context found: {len(context)} chars")
        
        print("6. Testing Groq API...")
        # سحب المفتاح من متغيرات البيئة
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            print("❌ Error: GROQ_API_KEY not found in environment")
            return
        client = Groq(api_key=api_key)
        
        completion = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {"role": "system", "content": "أنت مستشار ذكي متخصص في علم المواريث الإسلامي."},
                {"role": "user", "content": f"السياق:\n{context}\n\nالسؤال:\n{question}"}
            ]
        )
        print("7. Success! Response:")
        print(completion.choices[0].message.content)

    except Exception as e:
        print(f"❌ FAILED at stage: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_rag()
