import os
import django
import json
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case, Heir, PaymentSettlement, Asset, AssetComponent
from cases.views import _build_review_context

def debug_latest_case_heirs_with_self_healing():
    case = Case.objects.all().order_by('-id').first()
    if not case:
        print("No cases found.")
        return

    print(f"Triggering Self-Healing for Case: {case.id}...")
    # This will trigger the logic in _build_review_context
    _build_review_context(case)

    print(f"Checking Case: {case.display_case_number} (ID: {case.id})")
    heirs = Heir.objects.filter(case=case).order_by('id')
    
    results = []
    for h in heirs:
        assets_val = sum(a.value for a in h.allocated_assets.all())
        comp_val = sum(c.value for c in h.allocated_components.all())
        actual_total = assets_val + comp_val
        
        settlements = PaymentSettlement.objects.filter(case=case, payer=h)
        
        results.append({
            'name': h.name,
            'is_judge_confirmed': h.is_judge_confirmed,
            'allocated_share_field': float(h.allocated_share),
            'actual_assets_total': float(actual_total),
            'share_value': float(h.share_value),
            'diff_actual': float(actual_total - h.share_value),
            'settlements_count': settlements.count(),
            'settlements_data': [{'amount': float(s.amount), 'id': s.id, 'reason': s.reason} for s in settlements]
        })
    
    print(json.dumps(results, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    debug_latest_case_heirs_with_self_healing()
