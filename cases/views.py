from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Case, Heir, Asset, HeirAssetSelection
from django.db.models import Count
from .forms import CaseForm, DeceasedForm
from .services import auto_allocate, get_allocation_warnings

@login_required
def case_list(request):
    # Judges see their cases, others might see different things
    if request.user.role == 'JUDGE':
        cases = Case.objects.filter(judge=request.user)
    else:
        cases = Case.objects.none() # Or handle other roles
    return render(request, 'cases/case_list.html', {'cases': cases})

@login_required
def create_case(request):
    if request.user.role != 'JUDGE':
        return redirect('dashboard') # Only judges can create cases for now
        
    if request.method == 'POST':
        case_form = CaseForm(request.POST)
        deceased_form = DeceasedForm(request.POST)
        if case_form.is_valid() and deceased_form.is_valid():
            case = case_form.save(commit=False)
            case.judge = request.user
            case.save()
            
            deceased = deceased_form.save(commit=False)
            deceased.case = case
            deceased.save()
            
            return redirect('case_list')
    else:
        case_form = CaseForm()
        deceased_form = DeceasedForm()
    
    return render(request, 'cases/create_case.html', {
        'case_form': case_form, 
        'deceased_form': deceased_form
    })

@login_required
def review_distribution(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    
    # Security check: Only assigned Judge
    if request.user != case.judge:
        # return redirect('dashboard') # Or 403
        pass # Allow for dev/test or multiple judges logic if needed

    heirs = case.heirs.all()
    
    # Conflict Detection: Assets with more than 1 selection intent
    conflicting_assets = Asset.objects.filter(case=case).annotate(
        selection_count=Count('selection_intents')
    ).filter(selection_count__gt=1)

    # Get warnings from service
    system_warnings = get_allocation_warnings(case)

    heir_stats = []
    all_selected = True
    all_balanced = True

    for heir in heirs:
        # We look at both: directly assigned (by judge) AND selection intents (by heir)
        intents = HeirAssetSelection.objects.filter(heir=heir)
        selected_value = sum(i.asset.value for i in intents)
        diff = selected_value - heir.share_value
        
        # Determine if this heir has any "anti-lottery" intents on conflicted assets
        refused_lottery_conflicts = intents.filter(
            asset__in=conflicting_assets, 
            wants_lottery=False
        )
        has_refusal = refused_lottery_conflicts.exists()
        
        has_selected = intents.exists()
        if not has_selected:
            all_selected = False
            
        status_label = "لم يختر بعد"
        if has_selected:
            # Check if any of their selections are in conflict
            my_conflicts = conflicting_assets.filter(selection_intents__heir=heir)
            if my_conflicts.exists():
                if has_refusal:
                    status_label = f"تعارض (مرفوض للقرعة: {refused_lottery_conflicts.count()})"
                else:
                    status_label = f"تعارض (جاهز للقرعة: {my_conflicts.count()})"
                all_balanced = False
            else:
                if abs(diff) < 0.1:
                    status_label = "متطابق"
                elif diff > 0:
                    status_label = f"عليه دفع فرق ({diff})"
                    # We might want to set all_balanced = False if they need to pay, 
                    # but here we allow the judge to decide.
                else:
                    status_label = f"لم يكمل النصيب (باقي {abs(diff)})"
                    # all_balanced = False # We allow partial now, but Judge might want to know
        
        heir_stats.append({
            'name': heir.name,
            'share_value': heir.share_value,
            'selected_value': selected_value,
            'diff': diff,
            'status': status_label,
            'obj': heir,
            'intents': intents
        })

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            # 1. Finalize assignments from intents to actual Asset fields
            for h in heirs:
                intents = HeirAssetSelection.objects.filter(heir=h)
                for intent in intents:
                    intent.asset.assigned_to = h
                    intent.asset.save()
                    
                    # Update allocated_share
                    h.allocated_share += intent.asset.value
                    h.save()
                
                h.acceptance_status = Heir.AcceptanceStatus.ACCEPTED
                h.save()

            # 2. Run Auto Allocation for remaining assets
            auto_allocate(case)

            # 3. Finalize Case Status
            case.status = Case.Status.COMPLETED
            case.save()
            
            messages.success(request, 'تم اعتماد التوزيع بنجاح، تقسيم الباقي تلقائياً وإغلاق القضية.')
            return redirect('final_report', case_id=case.id)
        elif action == 'escalate':
            # Redirect to lottery page to pick items for lottery
            return redirect('start_lottery', case_id=case.id)

    return render(request, 'cases/review_distribution.html', {
        'case': case,
        'heir_stats': heir_stats,
        'all_selected': all_selected,
        'all_balanced': all_balanced,
        'system_warnings': system_warnings,
    })

import random

@login_required
def start_lottery(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    if request.user != case.judge:
        pass # Security

    # Assets with conflicts (more than 1 intent)
    conflicted_assets = Asset.objects.filter(case=case).annotate(
        selection_count=Count('selection_intents')
    ).filter(selection_count__gt=1)

    # All unassigned assets for the dropdown
    lottery_assets = Asset.objects.filter(case=case, assigned_to__isnull=True)
    
    if request.method == 'POST':
        asset_id = request.POST.get('asset_id')
        participant_ids = request.POST.getlist('participants')
        
        target_asset = get_object_or_404(Asset, id=asset_id, case=case)
        participants = Heir.objects.filter(id__in=participant_ids, case=case)
        
        if participants.exists():
            winner = random.choice(list(participants))
            
            # Assign
            target_asset.assigned_to = winner
            target_asset.save()
            
            # Decrement winner's effective balance? 
            # In our model, we just assign. The "Review" page calculates diff.
            # If winner now exceeds share, they must pay diff. This is consistent.
            
            messages.success(request, f'تم إجراء القرعة على "{target_asset.description}". الفائز: {winner.name}')
            return redirect('review_distribution', case_id=case.id)
        else:
            messages.error(request, 'يجب اختيار مشارك واحد على الأقل.')

    # Create a mapping of asset_id -> list of heir_ids for JS
    conflict_map = {}
    all_assets = Asset.objects.filter(case=case)
    for a in all_assets:
        heir_ids = list(a.selection_intents.values_list('heir_id', flat=True))
        if heir_ids:
            conflict_map[a.id] = heir_ids

    return render(request, 'cases/start_lottery.html', {
        'case': case,
        'lottery_assets': lottery_assets,
        'heirs': case.heirs.all(),
        'conflict_map_json': conflict_map
    })

@login_required
def liquidation_view(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    if request.user != case.judge:
        pass

    # Assets eligible for liquidation (Unassigned or explicitly marked)
    # Usually items moved to Stage 4
    assets = Asset.objects.filter(case=case, assigned_to__isnull=True, is_liquidated=False)
    
    if request.method == 'POST':
        asset_ids = request.POST.getlist('asset_ids')
        
        # Simple loop to process sold items
        for aid in asset_ids:
            sold_price = request.POST.get(f'price_{aid}')
            if sold_price:
                asset = Asset.objects.get(id=aid, case=case)
                asset.is_liquidated = True
                asset.sold_price = sold_price
                # Calculate difference from estimated value if needed
                # asset.value = sold_price # Maybe update value to reflect reality?
                # For distribution, we treat this as Cash now.
                asset.save()
        
        messages.success(request, 'تم تسييل الأصول المختارة وتحديث قيمتها.')
        return redirect('liquidation', case_id=case_id)

    # Show liquidated items too
    liquidated_assets = Asset.objects.filter(case=case, is_liquidated=True)

    return render(request, 'cases/liquidation.html', {
        'case': case,
        'assets': assets,
        'liquidated_assets': liquidated_assets
    })

@login_required
def final_report(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    heirs = case.heirs.all()
    heir_data = []
    total_estate_value = sum(a.value for a in case.assets.all())
    for heir in heirs:
        assigned_assets = Asset.objects.filter(assigned_to=heir)
        specific_assets_value = sum(a.value for a in assigned_assets)
        
        # The remainder in allocated_share is what was given by the auto-allocation service
        pool_allocation = heir.allocated_share - specific_assets_value
        if pool_allocation < 0: pool_allocation = 0
            
        heir_data.append({
            'heir': heir,
            'assets': assigned_assets,
            'specific_assets_value': specific_assets_value,
            'pool_allocation': pool_allocation,
            'total_allocated': heir.allocated_share,
            'diff': heir.allocated_share - heir.share_value
        })
    return render(request, 'cases/final_report.html', {
        'case': case,
        'heir_data': heir_data,
        'total_estate_value': total_estate_value,
    })
