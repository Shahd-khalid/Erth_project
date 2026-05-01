# اختيار نسخة بايثون خفيفة
FROM python:3.11-slim

# منع بايثون من كتابة ملفات .pyc وإرسال المخرجات مباشرة
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# تثبيت متطلبات النظام الأساسية (ضرورية لمكتبات مثل psycopg2)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# نسخ ملف المكتبات وتثبيتها أولاً (للاستفادة من كاش الدوكر)
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# نسخ جميع ملفات المشروع إلى الحاوية
COPY . /app/

# فتح المنفذ الذي سيعمل عليه الموقع
EXPOSE 8000

# الأمر الافتراضي للتشغيل (سنستخدم daphne لأنه يدعم الـ WebSockets في مشروعك، أو runserver للتطوير)
# نستخدم runserver هنا لتسهيل العرض على الدكتور
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
