from django.shortcuts import render
from django.http import JsonResponse
import json
import os
import requests
import time
import numpy as np
from groq import Groq
import faiss
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
# المتغيرات العالمية للكاش
load_dotenv()
_index = None
_chunks = None
_client_groq = None

def get_groq_client():
    global _client_groq
    if _client_groq is None:
        _client_groq = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _client_groq

def get_rag_resources():
    global _index, _chunks
    if _index is None:
        print("📥 Loading RAG index & chunks...")
        if os.path.exists("rag/index.faiss") and os.path.exists("rag/chunks.json"):
            _index = faiss.read_index("rag/index.faiss")
            with open("rag/chunks.json", "r", encoding="utf-8") as f:
                _chunks = json.load(f)
        else:
            print("⚠️ RAG resources not found. Run build_index.py first.")
    return _index, _chunks

def get_embedding(text):
    """Generate normalized embedding vector using BAAI/bge-m3."""
    hf_token = os.environ.get("HUGGINGFACE_API_KEY")
    model_id = "BAAI/bge-m3"
    
    if not hf_token:
        print("MISSING HUGGINGFACE_API_KEY")
        return None
        
    client = InferenceClient(token=hf_token)
    
    # 350 char limit
    safe_text = text[:350]
    
    for attempt in range(2):
        try:
            vector = client.feature_extraction(safe_text, model=model_id)
            if hasattr(vector, 'tolist'): vector = vector.tolist()
            
            if isinstance(vector, list) and len(vector) > 0:
                if isinstance(vector[0], list):
                    vector = vector[0]
                    if isinstance(vector[0], list):
                        vector = vector[0]
                
                if len(vector) > 0 and isinstance(vector[0], (int, float)):
                    return vector
        except Exception as e:
            print(f"Embedding Error: {e}")
            time.sleep(1)
    return None

def chat(request):
    try:
        question = request.GET.get("q")
        if not question:
            return JsonResponse({"answer": "اكتب سؤالك أولاً!"}, json_dumps_params={'ensure_ascii': False})

        # تحميل الكشاف والنصوص
        index, chunks = get_rag_resources()
        if not index or not chunks:
            return JsonResponse({"answer": "عذراً، قاعدة البيانات غير جاهزة حالياً."}, json_dumps_params={'ensure_ascii': False})

        # توليد Embedding للسؤال
        vector = get_embedding(question)
        if vector is None:
            return JsonResponse({"answer": "عذراً، خدمة معالجة النصوص تواجه ضغطاً حالياً."}, json_dumps_params={'ensure_ascii': False})
            
        question_embedding = np.array([vector]).astype('float32')

        # البحث في FAISS
        D, I = index.search(question_embedding, k=3)
        
        context = ""
        for i in I[0]:
            if i != -1 and i < len(chunks):
                context += chunks[i] + "\n"
        
        # إرسال إلى Groq للرد النهائي
        client_groq = get_groq_client()
        completion = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
                  messages=[
                {"role": "system", "content": """أنت خبير فقهي متخصص في علم الفرائض والمواريث. 
هدفك تقديم إجابة دقيقة وشاملة وصحيحة شرعاً بناءً على السياق المرفق.

قواعد صارمة للإجابة:
1. الشمولية في ذكر الحالات: عند السؤال عن نصيب أي وارث، يجب عليك ذكر جميع حالاته الشرعية الممكنة (مثلاً: الزوجة ترث الربع في حال عدم وجود فرع وارث، وترث الثمن في حال وجود فرع وارث). لا تكتفِ أبداً بذكر حالة واحدة فقط.
2. التحقق من اسم الوارث: تأكد تماماً أن النص المرفق يتحدث عن الوارث المطلوب في السؤال قبل الإجابة.
3. تجنب الأسهم الحسابية: اذكر الأنصبة كفروض (نصف، ربع، ثمن..) ولا تذكر عدد الأسهم (مثل 8 أسهم) إلا إذا طُلب منك حساب مسألة محددة.
4. الدقة الفقهية: الثمن للزوجة فقط، والربع للزوج أو الزوجة، والسدس والثلث للأم أو الورثة الآخرين حسب شروطهم.
5. في حال نقص المعلومات: إذا لم تجد كل الحالات في السياق، اذكر ما وجدته بوضوح وقل 'هذا ما ورد في المستندات'."""},

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

def chat_page(request):
    return render(request, "chat.html")  