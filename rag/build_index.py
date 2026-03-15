import os
import json
import numpy as np
import faiss
import time
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

def build_index():
    print("Starting RAG Super-Robust Index Build (BGE-M3)...")
    
    # 1. Load Chunks
    json_path = "rag/chunks.json"
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found. Run prepare_data.py first.")
        return
        
    with open(json_path, "r", encoding="utf-8") as f:
        all_chunks = json.load(f)
    
    print(f"Chunks to process: {len(all_chunks)}")
    
    # 2. HF Settings
    hf_token = os.environ.get("HUGGINGFACE_API_KEY")
    model_id = "BAAI/bge-m3"
    client = InferenceClient(token=hf_token)
    
    embeddings = []
    valid_chunks = []
    consecutive_failures = 0
    
    for i, chunk in enumerate(all_chunks):
        # 350 char limit
        safe_text = chunk[:350]
        success = False
        
        for attempt in range(3):
            try:
                # Use feature_extraction from InferenceClient
                vector = client.feature_extraction(safe_text, model=model_id)
                
                # Validation: check if it's a numeric list or numpy array
                if hasattr(vector, 'tolist'): vector = vector.tolist()
                
                if isinstance(vector, list) and len(vector) > 0:
                    # Sometimes returns [[vector]], flatten if needed
                    if isinstance(vector[0], list):
                        vector = vector[0]
                        if isinstance(vector[0], list): # deeper?
                            vector = vector[0]

                    # Final check: is it numeric?
                    if len(vector) > 0 and isinstance(vector[0], (int, float)):
                        embeddings.append(vector)
                        valid_chunks.append(chunk)
                        success = True
                        consecutive_failures = 0
                        break
                
                print(f"Chunk {i}: API returned non-numeric format. Attempt {attempt+1}")
                time.sleep(2)
            except Exception as e:
                if "503" in str(e) or "loading" in str(e).lower():
                    print(f"Model loading at chunk {i}... waiting 20s")
                    time.sleep(20)
                else:
                    print(f"Error at chunk {i}: {e}")
                    time.sleep(5)
        
        if not success:
            consecutive_failures += 1
            print(f"Skipping chunk {i}")
            if consecutive_failures >= 15:
                print("Circuit Breaker: Too many consecutive failures. Stopping.")
                break
        
        if (i + 1) % 10 == 0:
            print(f"Progress: {i + 1}/{len(all_chunks)} chunks processed...")

    if not embeddings:
        print("Error: No embeddings collected. Build failed.")
        return

    # 3. Build Index
    print(f"Processing {len(embeddings)} valid vectors...")
    try:
        lengths = [len(v) for v in embeddings]
        common_len = max(set(lengths), key=lengths.count)
        
        final_embeddings = [v for v in embeddings if len(v) == common_len]
        final_chunks = [c for c, v in zip(valid_chunks, embeddings) if len(v) == common_len]
        
        matrix = np.array(final_embeddings).astype('float32')
        print(f"Building FAISS Index (Dim: {common_len})...")
        
        index = faiss.IndexFlatL2(common_len)
        index.add(matrix)
        
        faiss.write_index(index, "rag/index.faiss")
        with open("rag/chunks.json", "w", encoding="utf-8") as f:
            json.dump(final_chunks, f, ensure_ascii=False)
            
        print(f"SUCCESS! Indexed {len(final_chunks)} chunks.")
    except Exception as e:
        print(f"Finalization Error: {e}")

if __name__ == "__main__":
    build_index()
