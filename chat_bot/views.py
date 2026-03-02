from django.shortcuts import render
from django.http import JsonResponse
import json
import os
import requests
import time
import numpy as np
from groq import Groq

# متغيرات عالمية سيتم تحميلها عند الحاجة (Lazy Loading)
_index = None
_chunks = None

# إعدادات API Hugging Face (بديل للموديل المحلي لتوفير الرام)
HF_API_URL = "https://api-inference.huggingface.co/models/intfloat/multilingual-e5-small"
# يفضل إضافة مفتاح Hugging Face في إعدادات Render لضمان استقرار الخدمة
HF_TOKEN = os.environ.get("HUGGINGFACE_API_KEY")

def query_huggingface(payload):
    headers = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
    for _ in range(3): # محاولة 3 مرات في حال كان الموديل في وضع السكون
        response = requests.post(HF_API_URL, headers=headers, json=payload)
        result = response.json()
        if isinstance(result, dict) and "error" in result and "currently loading" in result["error"]:
            time.sleep(5)
            continue
        return result
    return None

def get_rag_resources():
    global _index, _chunks
    if _index is None:
        print("📥 Loading RAG index & chunks...")
        import faiss # خفيف ولا يستهلك رام كبيرة
        _index = faiss.read_index("rag/index.faiss")
        with open("rag/chunks.json", "r", encoding="utf-8") as f:
            _chunks = json.load(f)
    return _index, _chunks

# تهيئة عميل Groq (سريع جداً وخفيف)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def chat(request):
    try:
        question = request.GET.get("q")
        if not question:
            return JsonResponse({"answer": "اكتب سؤالك أولاً!"}, json_dumps_params={'ensure_ascii': False})

        # تحميل الكشاف والنصوص فقط (بدون الموديل الثقيل)
        index, chunks = get_rag_resources()

        # طلب تحويل السؤال لـ Vector عبر API خارجي
        # الـ e5 model يحتاج كلمة 'query: ' قبل السؤال للبحث
        hf_result = query_huggingface({"inputs": f"query: {question}"})
        
        if hf_result and isinstance(hf_result, list):
            question_embedding = np.array(hf_result).astype('float32')
            if len(question_embedding.shape) == 1:
                question_embedding = question_embedding.reshape(1, -1)
        else:
            return JsonResponse({"answer": "عذراً، خدمة معالجة النصوص تواجه ضغطاً حالياً. يرجى المحاولة بعد لحظات."}, json_dumps_params={'ensure_ascii': False})
        
        # البحث في FAISS
        D, I = index.search(question_embedding, k=3)

        context = ""
        for i in I[0]:
            if i != -1: # التأكد أن البحث وجد نتيجة صحيحة
                context += chunks[i] + "\n"

        # إرسال إلى Groq
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "أنت مستشار ذكي متخصص في علم المواريث الإسلامي. أجب عن السؤال استناداً إلى السياق المرفق فقط. إذا لم تجد الإجابة في السياق والمستندات بوضوح، قل 'لا توجد معلومات كافية في المستندات للإجابة'."},
                {"role": "user", "content": f"السياق المرجعي:\n{context}\n\nالسؤال:\n{question}"}
            ],
            temperature=0.7,
            max_tokens=1024,
        )

        answer = completion.choices[0].message.content.strip()
        return JsonResponse({"answer": answer}, json_dumps_params={'ensure_ascii': False})
    
    except Exception as e:
        print(f"❌ Error in chat view: {e}")
        return JsonResponse({"answer": f"حدث خطأ فني: {str(e)}"}, status=500, json_dumps_params={'ensure_ascii': False})


from django.shortcuts import render

def chat_page(request):
    return render(request, "chat.html")