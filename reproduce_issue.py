import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case, Deceased, Heir
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

User = get_user_model()

def run():
    print("--- Reproduction Test ---")
    
    # 1. Setup Data
    judge = User.objects.filter(role='JUDGE').first()
    if not judge:
        judge = User.objects.create_user('judge_test', 'j@test.com', 'pass', role='JUDGE')
        
    clerk = User.objects.filter(role='CLERK').first()
    if not clerk:
        clerk = User.objects.create_user('clerk_test', 'c@test.com', 'pass', role='CLERK')
        
    case = Case.objects.create(case_number="CASE-999", judge=judge, clerk=clerk)
    print(f"Created Case: {case}")
    
    # 2. Clerk 'Saves' Deceased
    # Simulation of Clerk View Logic
    print("Clerk saving Deceased...")
    try:
        deceased = case.deceased
    except ObjectDoesNotExist: # Using base for safety in script
        deceased = None
        
    # Create new
    deceased = Deceased.objects.create(case=case, name="Old Deceased Name", date_of_death="2023-01-01", national_id="123")
    print(f"Deceased Created: {deceased.name}")
    
    # Verify link
    case.refresh_from_db()
    try:
        d = case.deceased
        print(f"Case.deceased exists: {d.name}")
    except Exception as e:
        print(f"ERROR: Case.deceased access failed: {e}")
        
    # 3. Judge View Logic
    print("Judge viewing case...")
    try:
        # The exact line from judges/views.py
        try:
            d_judge = case.deceased
        except Deceased.DoesNotExist:
            d_judge = None
            
        if d_judge:
            print(f"Judge FOUND Deceased: {d_judge.name}")
        else:
            print("Judge found NOTHING (None)")
            
    except Exception as e:
        print(f"Judge logic CRASHED: {e}")

    # clean up
    case.delete()

if __name__ == '__main__':
    run()
