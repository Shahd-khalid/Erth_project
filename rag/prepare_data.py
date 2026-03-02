import os
import fitz

DATA_FOLDER = "../knowledg_pdf"

def extract_text_from_folder(folder_path):
    all_chunks = []

    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf"):
            try:
                path = os.path.join(folder_path, filename)
                doc = fitz.open(path)

                text = ""
                for page in doc:
                    text += page.get_text()

                words = text.split()
                chunk_size = 300

                for i in range(0, len(words), chunk_size):
                    chunk = " ".join(words[i:i+chunk_size])
                    all_chunks.append(chunk)

                print(f"تمت قراءة {filename}")

            except Exception as e:
                print(f"❌ خطأ في الملف {filename}")
                print(e)

    return all_chunks


chunks = extract_text_from_folder(DATA_FOLDER)

import json
with open("chunks.json", "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False)

print("تم استخراج النص وتقسيمه ✅")