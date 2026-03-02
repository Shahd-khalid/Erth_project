import os
import json
import numpy as np
import faiss
import requests
import time
from groq import Groq

def query_huggingface(payload):
    HF_API_URL = "https://api-inference.huggingface.co/models/intfloat/multilingual-e5-small"
    HF_TOKEN = os.environ.get("HUGGINGFACE_API_KEY")
    headers = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
    for _ in range(3):
        response = requests.post(HF_API_URL, headers=headers, json=payload)
        result = response.json()
        if isinstance(result, dict) and "error" in result and "currently loading" in result["error"]:
            print("⏳ Model is loading, waiting...")
            time.sleep(5)
            continue
        return result
    return None

def test_rag():
    try:
        print("1. Loading Index...")
        index = faiss.read_index("rag/index.faiss")
        
        print("2. Loading Chunks...")
        with open("rag/chunks.json", "r", encoding="utf-8") as f:
            chunks = json.load(f)
            
        print("3. Testing API Encoding...")
        question = "كم نصيب الأم؟"
        hf_result = query_huggingface({"inputs": f"query: {question}"})
        
        if hf_result and isinstance(hf_result, list):
            question_embedding = np.array(hf_result).astype('float32')
            if len(question_embedding.shape) == 1:
                question_embedding = question_embedding.reshape(1, -1)
        else:
            print(f"❌ API Error: {hf_result}")
            return
        
        print("4. Testing FAISS Search...")
        D, I = index.search(question_embedding, k=3)
        
        context = ""
        for i in I[0]:
            if i != -1:
                context += chunks[i] + "\n"
        print(f"   Context found: {len(context)} chars")
        
        print("5. Testing Groq API...")
        # سحب المفتاح من متغيرات البيئة
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            print("❌ Error: GROQ_API_KEY not found in environment")
            return
        client = Groq(api_key=api_key)
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "أنت مستشار ذكي متخصص في علم المواريث الإسلامي."},
                {"role": "user", "content": f"السياق:\n{context}\n\nالسؤال:\n{question}"}
            ]
        )
        print("6. Success! Response:")
        print(completion.choices[0].message.content)

    except Exception as e:
        print(f"❌ FAILED at stage: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_rag()
