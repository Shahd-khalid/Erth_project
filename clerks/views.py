from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.forms import modelformset_factory
from cases.models import Case, Heir, Deceased, Asset, Debt, Will
from cases.forms import DeceasedForm, AssetForm, DebtForm, WillForm

@login_required
def dashboard(request):
    if request.user.role != 'CLERK':
        return redirect('dashboard:index')
        
    assigned_cases = Case.objects.filter(clerk=request.user, status=Case.Status.WITH_CLERK)
    
    # Cases submitted by clerk (waiting for judge or in calculation)
    submitted_cases = Case.objects.filter(
        clerk=request.user, 
        status__in=[
            Case.Status.DATA_REVIEW, 
            Case.Status.READY_FOR_CALCULATION, 
            Case.Status.COMPLETED
        ]
    )
    
    # Check for Pending Judge Request
    pending_request = False
    if request.user.assigned_judge and request.user.clerk_judge_status == request.user.ClerkJudgeStatus.PENDING:
        pending_request = True
        
    return render(request, 'clerks/dashboard.html', {
        'assigned_cases': assigned_cases,
        'submitted_cases': submitted_cases,
        'pending_request': pending_request,
        'assigned_judge': request.user.assigned_judge
    })

@login_required
def accept_judge(request):
    if request.user.role != 'CLERK' or request.method != 'POST':
        return redirect('dashboard:index')
        
    request.user.clerk_judge_status = request.user.ClerkJudgeStatus.APPROVED
    request.user.save()
    
    return redirect('clerks:dashboard')

@login_required
def reject_judge(request):
    if request.user.role != 'CLERK' or request.method != 'POST':
        return redirect('dashboard:index')
        
    # Reset assignment
    request.user.clerk_judge_status = request.user.ClerkJudgeStatus.PENDING # Or Reset completely
    request.user.assigned_judge = None
    request.user.save()
    
    return redirect('clerks:dashboard')

@login_required
def enter_case_data(request, case_id):
    if request.user.role != 'CLERK':
        return redirect('dashboard:index')
        
    case = get_object_or_404(Case, id=case_id, clerk=request.user)
    
    # Check if Deceased record exists
    try:
        deceased = case.deceased
    except Deceased.DoesNotExist:
        deceased = None
    
    HeirFormSet = modelformset_factory(Heir, fields=('name', 'relationship', 'gender'), extra=3, can_delete=True)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_asset':
            form = AssetForm(request.POST, request.FILES)
            if form.is_valid():
                asset = form.save(commit=False)
                asset.case = case
                asset.save()
            return redirect('clerks:enter_case_data', case_id=case.id)
            
        elif action == 'add_debt':
            form = DebtForm(request.POST)
            if form.is_valid():
                debt = form.save(commit=False)
                debt.case = case
                debt.save()
            return redirect('clerks:enter_case_data', case_id=case.id)
            
        elif action == 'add_will':
            form = WillForm(request.POST)
            if form.is_valid():
                will = form.save(commit=False)
                will.case = case
                will.save()
            return redirect('clerks:enter_case_data', case_id=case.id)

        elif action == 'save_basic' or action == 'save_heirs':
            # Handle Basic Info and Heirs
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
                # Handle deletions
                for obj in heir_formset.deleted_objects:
                    obj.delete()
                    
            return redirect('clerks:enter_case_data', case_id=case.id)
            
        elif action == 'submit_to_judge':
            case.status = Case.Status.DATA_REVIEW
            case.is_ready_for_calculation = False # Ensure false until approved
            case.save()
            return redirect('clerks:dashboard')
            
    else:
        deceased_form = DeceasedForm(instance=deceased)
        heir_formset = HeirFormSet(queryset=Heir.objects.filter(case=case))

    # Ensure locals are defined in case of fall-through
    if 'deceased_form' not in locals():
        deceased_form = DeceasedForm(instance=deceased)
    if 'heir_formset' not in locals():
        heir_formset = HeirFormSet(queryset=Heir.objects.filter(case=case))
        
    return render(request, 'clerks/enter_case_data.html', {
        'case': case,
        'deceased_form': deceased_form,
        'heir_formset': heir_formset,
        'asset_form': AssetForm(),
        'debt_form': DebtForm(),
        'will_form': WillForm()
    })
