import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case, Heir

session_link = '0ec8ded5-56c5-4018-949b-35a50b092dbb'
try:
    case = Case.objects.get(session_link=session_link)
    print(f"Case: {case.case_number} (ID: {case.id}) - Status: {case.status}")
    
    print("\nHeirs in this session:")
    for h in case.heirs.all():
        print(f"  - ID: {h.id}, Name: {h.name}, Acceptance: {h.acceptance_status}, Consent: {h.mutual_consent_status}")
    
except Case.DoesNotExist:
    print("Case with this session link not found.")
except Exception as e:
    print(f"Error: {e}")
