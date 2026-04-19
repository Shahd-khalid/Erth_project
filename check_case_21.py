import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case, Heir

def check_case_21():
    try:
        case = Case.objects.get(id=21)
        print(f"--- Case {case.id} ({case.case_number}) ---")
        print(f"Status: {case.status}")
        print(f"Judge Consents to Mutual: {case.judge_consents_to_mutual}")
        
        heirs = case.heirs.all()
        print(f"\nHeirs ({heirs.count()}):")
        for h in heirs:
            print(f" - {h.name}:")
            print(f"   Acceptance Status: {h.acceptance_status}")
            print(f"   Mutual Consent Status: {h.mutual_consent_status}")
            
        # Mocking the dashboard filter logic
        # all_agreed = not case.heirs.exclude(mutual_consent_status=Heir.MutualConsentStatus.AGREED).exists()
        not_agreed_heirs = list(case.heirs.exclude(mutual_consent_status=Heir.MutualConsentStatus.AGREED))
        all_agreed = len(not_agreed_heirs) == 0
        
        print(f"\nDashboard Logic Check:")
        print(f" - all_agreed: {all_agreed}")
        if not all_agreed:
            print(f"   (Heirs causing False: {[h.name for h in not_agreed_heirs]})")
            
        print(f" - Should appear in 'Consent Requests': {case.status == Case.Status.CONSENT_PENDING and not case.judge_consents_to_mutual and all_agreed}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_case_21()
