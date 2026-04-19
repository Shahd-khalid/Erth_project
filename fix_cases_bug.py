import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case
from cases.services import sync_case_heir_allocated_shares, auto_allocate

def fix_completed_cases():
    cases = Case.objects.filter(status=Case.Status.COMPLETED)
    for case in cases:
        print(f"Fixing Case {case.id}")
        sync_case_heir_allocated_shares(case)
        auto_allocate(case)
        
if __name__ == '__main__':
    fix_completed_cases()
