import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case

def list_cases():
    cases = Case.objects.all().order_by('-id')[:5]
    print("--- Latest 5 Cases ---")
    for c in cases:
        print(f"ID: {c.id} | Number: {c.case_number} | Status: {c.status}")

if __name__ == "__main__":
    list_cases()
