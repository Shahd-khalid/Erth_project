from django.shortcuts import render
from django.http import JsonResponse
from sentence_transformers import SentenceTransformer
import json
import faiss
import numpy as np

from groq import Groq
import os

import torch
# تقليل عدد الخيوط لتوفير الموارد على Render
torch.set_num_threads(1)

# متغيرات عالمية سيتم تحميلها عند الحاجة (Lazy Loading)
_model = None
_index = None
_chunks = None

def get_rag_resources():
    global _model, _index, _chunks
    if _model is None:
        print("📥 Loading RAG resources for the first time...")
        _model = SentenceTransformer("intfloat/multilingual-e5-small")
        _index = faiss.read_index("rag/index.faiss")
        with open("rag/chunks.json", "r", encoding="utf-8") as f:
            _chunks = json.load(f)
    return _model, _index, _chunks

# تهيئة عميل Groq (سريع جداً ولا يحتاج تحميل موديلات)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def chat(request):
    try:
        question = request.GET.get("q")
        if not question:
            return JsonResponse({"answer": "اكتب سؤالك أولاً!"}, json_dumps_params={'ensure_ascii': False})

        # تحميل الموارد فقط عند أول طلب لضمان تشغيل السيرفر بسرعة
        model, index, chunks = get_rag_resources()

        # تحويل السؤال إلى Vector والتأكد من النوع float32
        question_embedding = model.encode([question]).astype('float32')
        
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