import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case, Heir, Asset, HeirAssetSelection
from cases.services import auto_allocate

def test_auto_allocation_logic():
    print("Starting auto-allocation verification...")
    
    # 1. Create a dummy case
    case = Case.objects.create(case_number=f"TEST-{os.getpid()}")
    
    # 2. Create heirs with specific shares
    # Total estate value will be 1000
    h1 = Heir.objects.create(case=case, name="Heir 1", share_value=Decimal('600.00'))
    h2 = Heir.objects.create(case=case, name="Heir 2", share_value=Decimal('400.00'))
    
    # 3. Create assets
    a1 = Asset.objects.create(case=case, description="Asset 1", value=Decimal('200.00'))
    a2 = Asset.objects.create(case=case, description="Asset 2", value=Decimal('800.00'))
    
    # 4. Heir 1 selects Asset 1
    HeirAssetSelection.objects.create(heir=h1, asset=a1)
    
    # Simulate the "Approve" logic in view
    a1.assigned_to = h1
    a1.save()
    h1.allocated_share += a1.value
    h1.save()
    
    print(f"Before auto_allocate: h1={h1.allocated_share}, h2={h2.allocated_share}")
    
    # 5. Run auto_allocate for the remaining asset (a2)
    auto_allocate(case)
    
    # Refresh from DB
    h1.refresh_from_db()
    h2.refresh_from_db()
    
    print(f"After auto_allocate: h1={h1.allocated_share}, h2={h2.allocated_share}")
    
    # Total value should be 1000
    total = h1.allocated_share + h2.allocated_share
    print(f"Total Allocated: {total}")
    
    if total == 1000:
        print("SUCCESS: Auto-allocation distributed full estate value correctly.")
    else:
        print("FAILURE: Value mismatch.")
    
    # Cleanup
    case.delete()

if __name__ == "__main__":
    test_auto_allocation_logic()
