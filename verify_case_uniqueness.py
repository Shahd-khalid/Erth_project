import os
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case
from users.models import User
from django.db import IntegrityError

def test_case_uniqueness():
    # 1. Ensure we have two judges
    judge1, _ = User.objects.get_or_create(username='judge1', role=User.Role.JUDGE)
    judge2, _ = User.objects.get_or_create(username='judge2', role=User.Role.JUDGE)

    case_name = "CASE_TEST_001"

    # Cleanup existing cases with this name if any
    Case.objects.filter(case_number=case_name).delete()

    print(f"--- Testing uniqueness for case name: {case_name} ---")

    # 2. Judge 1 creates a case - should succeed
    try:
        c1 = Case.objects.create(case_number=case_name, judge=judge1)
        print(f"SUCCESS: Judge 1 created {case_name}")
    except Exception as e:
        print(f"FAILED: Judge 1 could not create {case_name}: {e}")
        return

    # 3. Judge 2 creates a case with SAME name - should succeed now!
    try:
        c2 = Case.objects.create(case_number=case_name, judge=judge2)
        print(f"SUCCESS: Judge 2 created SAME name {case_name}")
    except Exception as e:
        print(f"FAILED: Judge 2 could not create {case_name} (THIS SHOULD HAVE WORKED): {e}")

    # 4. Judge 1 tries to create another case with SAME name - should fail!
    try:
        c3 = Case.objects.create(case_number=case_name, judge=judge1)
        print(f"FAILED: Judge 1 created DUPLICATE name {case_name} (THIS SHOULD HAVE FAILED)")
    except IntegrityError:
        print(f"SUCCESS: Judge 1 correctly restricted from duplicate name {case_name}")
    except Exception as e:
        print(f"FAILED: Unexpected error for Judge 1 duplicate: {e}")

    # Cleanup
    Case.objects.filter(case_number=case_name).delete()

if __name__ == "__main__":
    test_case_uniqueness()
