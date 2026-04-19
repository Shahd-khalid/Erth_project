import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case, Heir

heir_id = 154
try:
    heir = Heir.objects.get(id=heir_id)
    case = heir.case
    print(f"Case: {case.case_number} (ID: {case.id}) - Status: {case.status}")
    print(f"Can open mutual balance (property): {case.can_open_mutual_balance}")
    
    print("\nHeirs:")
    for h in case.heirs.all():
        print(f"  - {h.name}: Acceptance={h.acceptance_status}, Consent={h.mutual_consent_status}")
    
    not_agreed = case.heirs.exclude(mutual_consent_status=Heir.MutualConsentStatus.AGREED)
    print(f"\nNot agreed count (using Enum): {not_agreed.count()}")
    
    not_agreed_str = case.heirs.exclude(mutual_consent_status="AGREED")
    print(f"Not agreed count (using string): {not_agreed_str.count()}")

except Exception as e:
    print(f"Error: {e}")
