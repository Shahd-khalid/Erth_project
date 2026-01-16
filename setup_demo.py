import os
import django
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from django.contrib.auth import get_user_model
from cases.models import Case, Heir, Asset, Deceased

User = get_user_model()

def run():
    print("--- Setting up Demo Data ---")
    
    # 1. Create Judge
    judge_username = "judge_demo"
    password = "password123"
    email = "judge@demo.com"
    
    if not User.objects.filter(username=judge_username).exists():
        judge = User.objects.create_user(username=judge_username, email=email, password=password, role='JUDGE')
        print(f"Created Judge: {judge_username} / {password}")
    else:
        judge = User.objects.get(username=judge_username)
        print(f"Judge exists: {judge_username}")

    # 2. Create Case
    case_num = "CASE-2025-DEMO"
    if not Case.objects.filter(case_number=case_num).exists():
        case = Case.objects.create(
            case_number=case_num,
            judge=judge,
            status=Case.Status.SESSION_ACTIVE, # Skip straight to active session
            judge_acceptance_status=Case.JudgeAcceptanceStatus.ACCEPTED,
            is_ready_for_calculation=True
        )
        Deceased.objects.create(case=case, name="المتوفى التجريبي", date_of_death="2024-01-01", national_id="1111111111")
        print(f"Created Case: {case_num}")
    else:
        case = Case.objects.get(case_number=case_num)
        print(f"Case exists: {case_num}")

    # 3. Create Heirs
    # Let's say Total Estate is 300,000.
    # Heir 1: Son (Takes ~200k)
    # Heir 2: Daughter (Takes ~100k)
    
    if not Heir.objects.filter(case=case, name="الابن أحمد").exists():
        h1 = Heir.objects.create(
            case=case, name="الابن أحمد", relationship=Heir.Relationship.SON, gender=Heir.Gender.MALE,
            share_value=200000.00, share_percentage=66.66
        )
    else:
        h1 = Heir.objects.get(case=case, name="الابن أحمد")

    if not Heir.objects.filter(case=case, name="الابنة سارة").exists():
        h2 = Heir.objects.create(
            case=case, name="الابنة سارة", relationship=Heir.Relationship.DAUGHTER, gender=Heir.Gender.FEMALE,
            share_value=100000.00, share_percentage=33.33
        )
    else:
        h2 = Heir.objects.get(case=case, name="الابنة سارة")

    print(f"Heirs Ready: {h1.name} (Share: {h1.share_value}), {h2.name} (Share: {h2.share_value})")

    # 4. Create Assets
    # Asset 1: Land (200k) - Perfect for Ahmed
    # Asset 2: Car (50k)
    # Asset 3: Gold (50k) 
    # Asset 4: Dispute House (100k) - For Lottery
    # Asset 5: Old Furniture (10k) - For Auction
    
    Asset.objects.get_or_create(case=case, description="أرض سكنية", defaults={'value': 200000, 'asset_type': Asset.AssetType.REAL_ESTATE})
    Asset.objects.get_or_create(case=case, description="سيارة تويوتا", defaults={'value': 50000, 'asset_type': Asset.AssetType.OTHER})
    Asset.objects.get_or_create(case=case, description="سبائك ذهب", defaults={'value': 50000, 'asset_type': Asset.AssetType.OTHER})
    Asset.objects.get_or_create(case=case, description="منزل شعبي (نزاع)", defaults={'value': 100000, 'asset_type': Asset.AssetType.REAL_ESTATE})
    Asset.objects.get_or_create(case=case, description="أثاث قديم (تصفية)", defaults={'value': 10000, 'asset_type': Asset.AssetType.OTHER})
    
    print("Assets Created.")
    
    print("\n--- DEMO LINKS ---")
    print(f"Judge Login: {judge_username} / {password}")
    print(f"Heir 1 (Ahmed) Link: http://127.0.0.1:8000/heirs/session/{case.session_link}/{h1.id}/select/")
    print(f"Heir 2 (Sara) Link:  http://127.0.0.1:8000/heirs/session/{case.session_link}/{h2.id}/select/")
    print(f"Judge Review: http://127.0.0.1:8000/cases/{case.id}/review/")
    print(f"Lottery:      http://127.0.0.1:8000/cases/{case.id}/lottery/")
    print(f"Liquidation:  http://127.0.0.1:8000/cases/{case.id}/liquidation/")
    
if __name__ == '__main__':
    run()
