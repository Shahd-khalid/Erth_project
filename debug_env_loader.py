import os
import dotenv

dotenv.load_dotenv()

print(f"DB_NAME: {os.environ.get('DB_NAME')}")
print(f"DB_USER: {os.environ.get('DB_USER')}")
pass_val = os.environ.get('DB_PASSWORD')
print(f"DB_PASSWORD Found: {pass_val is not None}")
if pass_val:
    print(f"DB_PASSWORD Length: {len(pass_val)}")
    print(f"DB_PASSWORD Starts with: {pass_val[:2]}...")
    
print(f"SECRET_KEY Found: {os.environ.get('SECRET_KEY') is not None}")
sk = os.environ.get('SECRET_KEY')
if sk:
    print(f"SECRET_KEY Length: {len(sk)}")
