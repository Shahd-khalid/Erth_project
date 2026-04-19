import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Case, Heir, Asset, HeirAssetSelection, AssetComponent
from django.db.models import Q

session_link = '0ec8ded5-56c5-4018-949b-35a50b092dbb' # From user's URL
case = Case.objects.get(session_link=session_link)

print(f"Case: {case.case_number} - Status: {case.status}")

for heir in case.heirs.all():
    print(f"\nHeir: {heir.name} (ID: {heir.id}) - Status: {heir.acceptance_status}")
    
    # Judge assignments
    assigned_assets = Asset.objects.filter(assigned_to=heir, case=case)
    assigned_comps = AssetComponent.objects.filter(assigned_to=heir, asset__case=case)
    
    print(f"  Judge Assignments: {assigned_assets.count()} assets, {assigned_comps.count()} components")
    for a in assigned_assets:
        print(f"    - Asset: {a.description}")
        # Check for manual selections from others
        manual_others = HeirAssetSelection.objects.filter(
            Q(asset=a) | Q(component__asset=a)
        ).exclude(heir=heir)
        if manual_others.exists():
            print(f"      !!!! CONFLICT DETECTED with manual selections:")
            for s in manual_others:
                print(f"        * Selected by {s.heir.name}")

    for c in assigned_comps:
        print(f"    - Component: {c.description}")
        manual_others = HeirAssetSelection.objects.filter(
            Q(component=c) | Q(asset=c.asset)
        ).exclude(heir=heir)
        if manual_others.exists():
            print(f"      !!!! CONFLICT DETECTED with manual selections:")
            for s in manual_others:
                print(f"        * Selected by {s.heir.name}")

    # Manual selections
    manual_selections = HeirAssetSelection.objects.filter(heir=heir)
    print(f"  Manual Selections: {manual_selections.count()}")
    for s in manual_selections:
        item = s.asset or s.component
        print(f"    - {item.description} (Status: {s.status})")
