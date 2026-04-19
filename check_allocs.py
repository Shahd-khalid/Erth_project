import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import PaymentSettlement, EstateObligationAllocation, Debt

def check_debt_allocations(debt_id):
    debt = Debt.objects.get(id=debt_id)
    allocs = EstateObligationAllocation.objects.filter(debt=debt)
    print(f"--- Allocations for Debt {debt.id} ({debt.description}) ---")
    print(f"Target Value: {debt.amount}")
    total = 0
    for a in allocs:
        print(f"ID: {a.id} | Amount: {a.allocated_amount} | Asset: {a.asset} | Settlement: {a.settlement}")
        total += a.allocated_amount
    print(f"Total Allocated in DB: {total}")

if __name__ == "__main__":
    check_debt_allocations(20)
