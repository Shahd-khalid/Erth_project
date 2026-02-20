from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from cases.models import Case, Asset, Debt, Will, Heir, Deceased, HeirAssetSelection
from cases.forms import AssetForm, DebtForm, WillForm, DeceasedForm
from django.forms import modelformset_factory
from calculator.engine import InheritanceEngine

User = get_user_model()

@login_required
def dashboard(request):
    if request.user.role != 'JUDGE':
        return redirect('dashboard:index') # Redirect to main dashboard if not judge
        
    # Cases assigned but waiting for Judge Acceptance
    new_cases = Case.objects.filter(
        judge=request.user, 
        judge_acceptance_status=Case.JudgeAcceptanceStatus.PENDING
    )
    
    # Active cases (Accepted by Judge)
    active_cases = Case.objects.filter(
        judge=request.user,
        judge_acceptance_status=Case.JudgeAcceptanceStatus.ACCEPTED
    )
    
    # Cases Waiting for Data Review (DATA_REVIEW)
    review_cases = Case.objects.filter(
        judge=request.user,
        status=Case.Status.DATA_REVIEW
    )

    # Active Sessions
    session_cases = Case.objects.filter(
        judge=request.user,
        status=Case.Status.SESSION_ACTIVE
    )
    
    # My Clerks (Only show approved ones or indicate status)
    # Let's show all assigned, but template can distinguish
    my_clerks = User.objects.filter(role=User.Role.CLERK, assigned_judge=request.user)
    
    return render(request, 'judges/dashboard.html', {
        'new_cases': new_cases, 
        'review_cases': review_cases,
        'session_cases': session_cases,
        'active_cases': active_cases,
        'my_clerks': my_clerks
    })

@login_required
def clerk_list(request):
    if request.user.role != 'JUDGE':
        return redirect('dashboard:index')
        
    # Clerks not assigned to any judge
    available_clerks = User.objects.filter(role=User.Role.CLERK, assigned_judge__isnull=True)
    my_clerks = User.objects.filter(role=User.Role.CLERK, assigned_judge=request.user)
    
    return render(request, 'judges/clerk_list.html', {
        'available_clerks': available_clerks,
        'my_clerks': my_clerks
    })

@login_required
def select_clerk(request, clerk_id):
    if request.user.role != 'JUDGE' or request.method != 'POST':
        return redirect('dashboard:index')
        
    clerk = get_object_or_404(User, id=clerk_id, role=User.Role.CLERK)
    
    # Ensure clerk is not already assigned (double check)
    if not clerk.assigned_judge:
        clerk.assigned_judge = request.user
        clerk.clerk_judge_status = User.ClerkJudgeStatus.PENDING # Set to Pending
        clerk.save()
        
    return redirect('judges:manage_clerks')

@login_required
def accept_case(request, case_id):
    if request.user.role != 'JUDGE' or request.method != 'POST':
        return redirect('dashboard:index')

    case = get_object_or_404(Case, id=case_id, judge=request.user)
    case.judge_acceptance_status = Case.JudgeAcceptanceStatus.ACCEPTED
    # Keep main Status as ASSIGNED_TO_JUDGE until they assign a clerk or start working
    case.save()
    
    return redirect('judges:dashboard')

@login_required
def reject_case(request, case_id):
    if request.user.role != 'JUDGE' or request.method != 'POST':
        return redirect('dashboard:index')

    case = get_object_or_404(Case, id=case_id, judge=request.user)
    case.judge_acceptance_status = Case.JudgeAcceptanceStatus.REJECTED
    case.judge = None # Unassign the judge so it can be reassigned
    case.status = Case.Status.PENDING # Back to Pending Pool
    case.save()
    
    return redirect('judges:dashboard')

@login_required
def assign_clerk(request, case_id):
    if request.user.role != 'JUDGE':
        return redirect('dashboard:index')
        
    case = get_object_or_404(Case, id=case_id, judge=request.user)
    clerks = User.objects.filter(role=User.Role.CLERK)
    
    if request.method == 'POST':
        clerk_id = request.POST.get('clerk_id')
        clerk = get_object_or_404(User, id=clerk_id)
        
        case.clerk = clerk
        case.status = Case.Status.WITH_CLERK
        case.save()
        
        return redirect('judges:dashboard')
        
    return render(request, 'judges/assign_clerk.html', {'case': case, 'clerks': clerks})

@login_required
def case_details(request, case_id):
    if request.user.role != 'JUDGE':
        return redirect('dashboard:index')
        
    case = get_object_or_404(Case, id=case_id, judge=request.user)
    
    # Check if Deceased record exists
    try:
        deceased = case.deceased
    except Deceased.DoesNotExist:
        deceased = None

    HeirFormSet = modelformset_factory(Heir, fields=('name', 'relationship', 'gender'), extra=0, can_delete=True)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_asset':
            form = AssetForm(request.POST, request.FILES)
            if form.is_valid():
                asset = form.save(commit=False)
                asset.case = case
                asset.save()
        elif action == 'add_debt':
            form = DebtForm(request.POST)
            if form.is_valid():
                debt = form.save(commit=False)
                debt.case = case
                debt.save()
        elif action == 'add_will':
            form = WillForm(request.POST)
            if form.is_valid():
                will = form.save(commit=False)
                will.case = case
                will.save()
        
        elif action == 'delete_asset':
            asset_id = request.POST.get('id')
            Asset.objects.filter(id=asset_id, case=case).delete()
        elif action == 'delete_debt':
            debt_id = request.POST.get('id')
            Debt.objects.filter(id=debt_id, case=case).delete()
        elif action == 'delete_will':
            will_id = request.POST.get('id')
            Will.objects.filter(id=will_id, case=case).delete()
        
        elif action == 'save_details':
             # Save Deceased and Heirs
            deceased_form = DeceasedForm(request.POST, instance=deceased)
            heir_formset = HeirFormSet(request.POST, queryset=Heir.objects.filter(case=case))
            
            if deceased_form.is_valid() and heir_formset.is_valid():
                deceased_obj = deceased_form.save(commit=False)
                deceased_obj.case = case
                deceased_obj.save()
                
                heirs = heir_formset.save(commit=False)
                for heir in heirs:
                    heir.case = case
                    heir.save()
                for obj in heir_formset.deleted_objects:
                    obj.delete()

        elif action == 'link_heir':
            heir_user_id = request.POST.get('heir_user_id')
            heir_user = get_object_or_404(User, id=heir_user_id, role=User.Role.HEIR)
            
            # Create a new Heir record for this case, linking back to the user
            # We use the relationship and name from the user's registry
            Heir.objects.create(
                case=case,
                user=heir_user,
                name=heir_user.full_name or heir_user.username,
                relationship=heir_user.relationship_to_deceased or Heir.Relationship.SON, # Default to SON if not specified, though usually captured
                gender=Heir.Gender.MALE # Simplified gender, better to capture in User reg too if needed
            )
            messages.success(request, f'تم ربط الوريث {heir_user.username} بالقضية بنجاح.')

        # Approve Case Details (Transition to Ready for Calculation)
        elif action == 'approve_details':
             # Validate before approving?
             case.is_ready_for_calculation = True
             case.status = Case.Status.READY_FOR_CALCULATION
             case.save()
             return redirect('judges:case_details', case_id=case.id)

        return redirect('judges:case_details', case_id=case.id)
        
    else:
        deceased_form = DeceasedForm(instance=deceased)
        heir_formset = HeirFormSet(queryset=Heir.objects.filter(case=case))

    # Get registered users who claimed to be heirs of this deceased
    if deceased:
        pending_heirs = User.objects.filter(
            role=User.Role.HEIR, 
            deceased_name__icontains=deceased.name,
            heir_records__isnull=True # Not yet linked to a case
        )
    else:
        pending_heirs = []

    return render(request, 'judges/case_details.html', {
        'case': case,
        'asset_form': AssetForm(),
        'debt_form': DebtForm(),
        'will_form': WillForm(),
        'deceased_form': deceased_form,
        'heir_formset': heir_formset,
        'pending_heirs': pending_heirs
    })

@login_required
def perform_calculation(request, case_id):
    if request.user.role != 'JUDGE':
        return redirect('dashboard:index')
    
    case = get_object_or_404(Case, id=case_id, judge=request.user)
    
    # 1. Calculate Financials
    total_assets = sum(a.value for a in case.assets.all())
    total_debts = sum(d.amount for d in case.debts.all())
    total_wills = sum(w.amount for w in case.wills.all())
    
    # Net Estate Logic
    net_after_debt = total_assets - total_debts
    
    # Will 1/3 Rule Check
    max_will = net_after_debt / 3
    effective_wills = min(total_wills, max_will) # Simple logic for now
    
    net_estate = net_after_debt - effective_wills
    
    if net_estate < 0:
        net_estate = 0 # Or handle error
        
    # 2. Call Engine
    
    # Prepare heirs data
    heirs_data = list(case.heirs.all())
    
    engine = InheritanceEngine(net_estate, heirs_data)
    
    results = engine.calculate()
    
    # 3. Save Results
    final_results = []
    blocked_heirs = []
    
    for heir_id, data in results.items():
        # Find the original heir object
        heir_obj = next((h for h in heirs_data if h.id == heir_id), None)
        if heir_obj:
            # Save to database
            heir_obj.share_percentage = data.get('percentage', 0)
            heir_obj.share_value = data['value']
            heir_obj.is_blocked = data.get('is_blocked', False)
            heir_obj.save()

            item = {
                'name': heir_obj.name,
                'relationship': heir_obj.get_relationship_display(),
                'fraction': data['fraction'],
                'value': data['value'],
                'percentage': data.get('percentage', 0),
                'is_blocked': data.get('is_blocked', False),
                'blocking_reason': data.get('blocking_reason', '')
            }
            
            if item['is_blocked']:
                heir_obj.blocking_reason = data.get('blocking_reason', '')
                heir_obj.save()
                blocked_heirs.append(item)
            else:
                final_results.append(item)

    return render(request, 'judges/calculation_result.html', {
        'case': case,
        'total_assets': total_assets,
        'total_debts': total_debts,
        'total_wills': total_wills,
        'effective_wills': effective_wills,
        'net_estate': net_estate,
        'results': final_results,
        'blocked_heirs': blocked_heirs
    })

@login_required
def allocate_assets(request, case_id):
    if request.user.role != 'JUDGE':
        return redirect('dashboard:index')

    case = get_object_or_404(Case, id=case_id, judge=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'save_allocation':
            # Iterate over assets and save assignment
            for asset in case.assets.all():
                heir_id = request.POST.get(f'asset_{asset.id}')
                if heir_id:
                    heir = get_object_or_404(Heir, id=heir_id, case=case)
                    asset.assigned_to = heir
                    asset.is_locked = True # Lock it initially if assigned
                    asset.save()
                else:
                    asset.assigned_to = None
                    asset.save()
            
            # Iterate over heirs and save description/share
            for heir in case.heirs.all():
                desc = request.POST.get(f'desc_{heir.id}')
                share_val = request.POST.get(f'value_{heir.id}') # Allow manual override or saving calc value
                
                if desc:
                    heir.allocation_description = desc
                if share_val:
                    heir.share_value = share_val
                
                heir.save()
                
            return redirect('judges:allocate_assets', case_id=case.id)
            
        elif action == 'publish_session':
             case.status = Case.Status.SESSION_ACTIVE
             case.save()
             # Link is available at case.session_link
             return redirect('judges:dashboard')

    # Get heir intents to suggest selections
    intents = HeirAssetSelection.objects.filter(asset__case=case)
    intent_map = {}
    for intent in intents:
        if intent.asset_id in intent_map:
            intent_map[intent.asset_id] = 'CONFLICT'
        else:
            intent_map[intent.asset_id] = intent.heir_id

    assets = case.assets.all()
    heirs = case.heirs.all()
    
    # Pre-process assets with their 'suggested' heir
    for asset in assets:
        asset.intent_heir_id = intent_map.get(asset.id)
        # We'll attach a list of enhanced heir objects to each asset for easy template selection
        enhanced_heirs = []
        for heir in heirs:
            is_selected = False
            is_suggested = False
            
            if asset.assigned_to_id == heir.id:
                is_selected = True
            elif not asset.assigned_to and asset.intent_heir_id == heir.id:
                is_selected = True
                is_suggested = True
            
            enhanced_heirs.append({
                'id': heir.id,
                'name': heir.name,
                'is_selected': is_selected,
                'is_suggested': is_suggested
            })
        asset.heir_options = enhanced_heirs

    return render(request, 'judges/allocate_assets.html', {
        'case': case,
        'assets': assets,
        'heirs': heirs,
    })
