import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import PaymentSettlement, EstateObligationAllocation, Case

def debug_settlements(case_id):
    case = Case.objects.get(id=case_id)
    settlements = PaymentSettlement.objects.filter(case=case)
    print(f"--- Debugging Settlements for Case {case_id} ---")
    for s in settlements:
        alloc_count = EstateObligationAllocation.objects.filter(settlement=s).count()
        print(f"ID: {s.id} | Payer: {s.payer.name if s.payer else 'None'} | Original Owner (Recipient): {s.original_owner.name if s.original_owner else 'None (Estate)'} | Amount: {s.amount} | Reason: {s.reason[:50]} | Alloc Count: {alloc_count}")

if __name__ == "__main__":
    debug_settlements(21)
