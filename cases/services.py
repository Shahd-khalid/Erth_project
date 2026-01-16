from decimal import Decimal
from django.db.models import Sum
from .models import Asset, Heir, HeirAssetSelection

def auto_allocate(case):
    """
    Distributes remaining unassigned assets among heirs proportionally 
    to their remaining share value.
    """
    unassigned_assets = Asset.objects.filter(case=case, assigned_to__isnull=True, is_liquidated=False)
    if not unassigned_assets.exists():
        return
    
    total_remaining_assets_value = unassigned_assets.aggregate(total=Sum('value'))['total'] or Decimal('0')
    heirs = case.heirs.all()
    
    # Calculate who still needs more
    heirs_needing_more = []
    total_shares_needing_more = Decimal('0')
    
    for heir in heirs:
        rem = heir.remaining_share()
        if rem > 0:
            heirs_needing_more.append((heir, rem))
            total_shares_needing_more += rem
            
    if total_shares_needing_more == 0:
        # Everyone got their share or more, assets stay unassigned or go to a general pool
        return

    # Proportional distribution of the total unassigned value
    # In a real system, we might assign specific assets, but here we update the allocated_share 
    # to show that the system has "given" them this value from the remaining pool.
    for heir, rem in heirs_needing_more:
        proportion = rem / total_shares_needing_more
        allocated_from_pool = total_remaining_assets_value * proportion
        heir.allocated_share += allocated_from_pool
        heir.save()
        
    # Mark assets as assigned to a "General Pool" or distribute them?
    # Usually, "Auto Allocation" means the residue is split.
    # We'll mark them as assigned to the first heir or just note they are distributed?
    # Let's assign them to the heirs if we want them to show up in the report.
    # Simple strategy: keep assets unassigned but the value is reflected in the heirs' total.
    # Or: Actually assign them if they are small, but for now, we'll just update the heir's allocated_share.
    pass

def get_allocation_warnings(case):
    """
    Returns a list of warnings for the judge:
    - Heirs who haven't selected anything.
    - Heirs whose selection exceeds their share.
    """
    warnings = []
    heirs = case.heirs.all()
    
    for heir in heirs:
        selections = HeirAssetSelection.objects.filter(heir=heir)
        if not selections.exists():
            warnings.append({
                'type': 'no_selection',
                'heir': heir,
                'message': f"الوريث {heir.name} لم يقم باختيار أي شيء بعد."
            })
        
        selected_value = sum(s.asset.value for s in selections)
        if selected_value > heir.share_value:
            diff = selected_value - heir.share_value
            warnings.append({
                'type': 'over_selection',
                'heir': heir,
                'diff': diff,
                'message': f"الوريث {heir.name} اختار أصولاً بقيمة {selected_value}، وهي تتجاوز نصيبه بمقدار {diff}."
            })
            
    return warnings
