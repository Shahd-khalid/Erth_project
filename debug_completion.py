import os
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case, Heir, Debt, Will, PaymentSettlement, DisputeRaffle
from cases.services import are_case_obligations_settled, get_case_judge_completion_status

def debug_all_cases():
    cases = Case.objects.exclude(status='COMPLETED')
    for case in cases:
        print(f"\n--- Debugging Case {case.id} ({case.deceased.name if getattr(case, 'deceased', None) else 'No Deceased'}) ---")
        print(f"Status: {case.status}")
        
        heirs = case.heirs.all()
        print(f"Heirs ({heirs.count()}):")
        for h in heirs:
            print(f"- {h.name}: Status={h.get_acceptance_status_display()}, Judge Confirmed={h.is_judge_confirmed}")
        
        all_heirs_approved = heirs.exists() and not heirs.exclude(
            acceptance_status=Heir.AcceptanceStatus.ACCEPTED,
            is_judge_confirmed=True,
        ).exists()
        print(f"All Heirs Approved: {all_heirs_approved}")

        active_disputes = DisputeRaffle.objects.filter(case=case, is_resolved=False)
        print(f"Active Disputes ({active_disputes.count()}):")
        for d in active_disputes:
            print(f"- Dispute on {d.asset or d.component}")

        pending_payments = PaymentSettlement.objects.filter(case=case, is_paid_to_judge=False)
        print(f"Pending Payments ({pending_payments.count()}):")
        for p in pending_payments:
            print(f"- Payment of {p.amount} from {p.payer}")

        obligations_settled = are_case_obligations_settled(case)
        print(f"Obligations Settled: {obligations_settled}")
        
        status = get_case_judge_completion_status(case)
        print(f"Overall Ready: {status['ready']}")

if __name__ == "__main__":
    debug_all_cases()
