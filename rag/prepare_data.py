import os
import fitz
import json

# المجلد الذي يحتوي على ملفات PDF
DATA_FOLDER = "knowledg_pdf"

def extract_text_from_folder(folder_path):
    all_chunks = []
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' not found!")
        return []
        
    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf"):
            path = os.path.join(folder_path, filename)
            print(f"Processing: {filename}")
            try:
                doc = fitz.open(path)
                text = ""
                for page in doc:
                    text += page.get_text()

                words = text.split()
                # 80 words for safety
                chunk_size = 80

                for i in range(0, len(words), chunk_size):
                    chunk = " ".join(words[i:i+chunk_size])
                    if len(chunk.strip()) > 10:
                        all_chunks.append(chunk)
            except Exception as e:
                print(f"Error reading {filename}: {e}")
    return all_chunks

if __name__ == "__main__":
    print("Cleaning old chunks...")
    if not os.path.exists("rag"):
        os.makedirs("rag", exist_ok=True)
        
    chunks = extract_text_from_folder(DATA_FOLDER)
    
    with open("rag/chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False)

    print(f"Created {len(chunks)} chunks in rag/chunks.json")