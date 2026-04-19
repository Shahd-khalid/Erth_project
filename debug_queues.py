import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case, Heir
from judges.views import get_case_judge_completion_status

def print_debug():
    cases = Case.objects.all()
    for case in cases:
        print(f"--- Case {case.id} ---")
        print(f"Status: {case.status}, Judge Consents: {case.judge_consents_to_mutual}")
        status = get_case_judge_completion_status(case)
        print(f"Completed Status Ready? {status['ready']}")
        if status['ready']:
            print(f"   -> all_heirs_approved: {status['all_heirs_approved']}")
            for h in case.heirs.all():
                print(f"      - Heir {h.id} acceptance: {h.acceptance_status}")

if __name__ == '__main__':
    print_debug()
