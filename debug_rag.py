import os
import json
import numpy as np
import faiss
import requests
import time
from groq import Groq
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

def query_hf_embedding(text):
    HF_TOKEN = os.environ.get("HUGGINGFACE_API_KEY")
    # موديل مايكروسوفت العالمي - مضمون لخاصية feature-extraction
    MODEL_ID = "microsoft/Multilingual-MiniLM-L12-H384"
    # الرابط الجديد المعتمد كبديل للرابط القديم
    url = f"https://router.huggingface.co/hf-inference/models/{MODEL_ID}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    
    try:
        # 350 حرف هو الأضمن للغة العربية
        safe_text = text[:350]
        response = requests.post(url, headers=headers, json={"inputs": safe_text}, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            
            # فحص صارم للنتيجة
            if isinstance(result, list) and len(result) > 0:
                # التعامل مع الـ Tensor (3D/2D)
                if isinstance(result[0], list):
                    if isinstance(result[0][0], list):
                        vector = result[0][0] # CLS
                    else:
                        vector = result[0]
                else:
                    vector = result
                
                # التأكد أنها قائمة أرقام
                if isinstance(vector, list) and isinstance(vector[0], (int, float)):
                    return vector
            
            print(f"⚠️ Debug: API returned unexpected format: {result}")
            return None
        elif response.status_code in [503, 404]:
            print(f"⏳ Model is loading, please wait...")
            return None
        else:
            print(f"❌ HF API Error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"❌ HF connection error: {e}")
        return None

def test_rag():
    try:
        print("1. Loading Index...")
        index = faiss.read_index("rag/index.faiss")
        
        print("2. Loading Chunks...")
        with open("rag/chunks.json", "r", encoding="utf-8") as f:
            chunks = json.load(f)
            
        print("3. Connecting to Groq...")
        groq_key = os.environ.get("GROQ_API_KEY")
        client_groq = Groq(api_key=groq_key)

        print("4. Testing HF Encoding...")
        question = "كم نصيب الأم؟"
        embedding = query_hf_embedding(question)
        
        if embedding is not None:
            question_embedding = np.array([embedding]).astype('float32')
        else:
            return
        
        print("5. Testing FAISS Search...")
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
