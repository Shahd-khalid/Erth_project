import os
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

def debug_api():
    hf_token = os.environ.get("HUGGINGFACE_API_KEY")
    client = InferenceClient(token=hf_token)
    
    # List of candidate multilingual models for embeddings
    models = [
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "google-bert/bert-base-multilingual-uncased",
        "symanto/sn-xlm-roberta-base-snli-mnli-anli-xnli",
        "BAAI/bge-m3"
    ]
    
    test_text = "passage: This is a test chunk."
    
    for model_id in models:
        print(f"\n--- Testing Model: {model_id} ---")
        try:
            # We explicitly want feature_extraction (embeddings)
            vector = client.feature_extraction(test_text, model=model_id)
            print(f"Success! Vector length: {len(vector)}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    debug_api()
