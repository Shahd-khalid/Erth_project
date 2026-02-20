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
    
    HeirFormSet = modelformset_factory(Heir, fields=('name', 'relationship', 'gender'), extra=0, can_delete=True)
    
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

        elif action == 'save_basic':
            deceased_form = DeceasedForm(request.POST, instance=deceased)
            if deceased_form.is_valid():
                deceased_obj = deceased_form.save(commit=False)
                deceased_obj.case = case
                deceased_obj.save()
                return redirect('clerks:enter_case_data', case_id=case.id)
            
        elif action == 'save_heirs':
            heir_formset = HeirFormSet(request.POST, queryset=Heir.objects.filter(case=case))
            if heir_formset.is_valid():
                heirs = heir_formset.save(commit=False)
                for heir in heirs:
                    heir.case = case
                    heir.save()
                for obj in heir_formset.deleted_objects:
                    obj.delete()
                return redirect('clerks:enter_case_data', case_id=case.id)
            # If invalid, deceased_form needs to be initialized for rendering below
            
        elif action == 'link_heir':
            heir_user_id = request.POST.get('heir_user_id')
            heir_user = get_object_or_404(User, id=heir_user_id, role=User.Role.HEIR)
            gender_map = {'MALE': 'ذكر', 'FEMALE': 'أنثى'}
            rel_map = {'SON': 'ابن', 'DAUGHTER': 'بنت', 'WIFE': 'زوجة', 'HUSBAND': 'زوج', 'FATHER': 'أب', 'MOTHER': 'أم'}
            
            u_gender = heir_user.gender
            if u_gender in gender_map: u_gender = gender_map[u_gender]
            
            u_rel = heir_user.relationship_to_deceased
            if u_rel in rel_map: u_rel = rel_map[u_rel]

            Heir.objects.create(
                case=case,
                user=heir_user,
                name=heir_user.full_name or heir_user.username,
                relationship=u_rel or Heir.Relationship.SON,
                gender=u_gender or Heir.Gender.MALE 
            )
            return redirect('clerks:enter_case_data', case_id=case.id)
            
        elif action == 'submit_to_judge':
            case.status = Case.Status.DATA_REVIEW
            case.is_ready_for_calculation = False # Ensure false until approved
            case.save()
            return redirect('clerks:dashboard')

        # Ensure these are defined for the final render if no redirect happened above
        if 'deceased_form' not in locals():
            deceased_form = DeceasedForm(instance=deceased)
        if 'heir_formset' not in locals():
            heir_formset = HeirFormSet(queryset=Heir.objects.filter(case=case))
            
    else:
        # Pre-fix data in DB to avoid SON/MALE English codes
        heirs_to_fix = Heir.objects.filter(case=case)
        gender_map = {'MALE': 'ذكر', 'FEMALE': 'أنثى'}
        rel_map = {'SON': 'ابن', 'DAUGHTER': 'بنت', 'WIFE': 'زوجة', 'HUSBAND': 'زوج', 'FATHER': 'أب', 'MOTHER': 'أم'}
        
        for h in heirs_to_fix:
            changed = False
            if h.gender in gender_map:
                h.gender = gender_map[h.gender]; changed = True
            if h.relationship in rel_map:
                h.relationship = rel_map[h.relationship]; changed = True
            
            # Also sync from user profile if linked and data is missing
            if h.user:
                if (not h.gender or h.gender in ['', 'MALE', 'FEMALE']) and h.user.gender:
                    u_gender = h.user.gender
                    h.gender = gender_map.get(u_gender, u_gender); changed = True
                if (not h.relationship or h.relationship in ['', 'SON']) and h.user.relationship_to_deceased:
                    u_rel = h.user.relationship_to_deceased
                    h.relationship = rel_map.get(u_rel, u_rel); changed = True
            
            if changed: h.save()

        deceased_form = DeceasedForm(instance=deceased)
        heir_formset = HeirFormSet(queryset=Heir.objects.filter(case=case))

    # Get registered users who claimed to be heirs of this deceased
    from users.models import User
    from django.db.models import Count
    
    # Try to pre-populate deceased name if empty or default
    if not deceased or not deceased.name or deceased.name in ['', 'احمدمحمد', 'موقت', 'متوفى']:
        # Check if any heirs are ALREADY linked to this case
        linked_heir = Heir.objects.filter(case=case, user__isnull=False).first()
        if linked_heir and linked_heir.user.deceased_name:
            new_name = linked_heir.user.deceased_name
            if not deceased_form.initial.get('name') or deceased_form.initial.get('name') in ['', 'احمدمحمد', 'موقت', 'متوفى']:
                deceased_form.initial['name'] = new_name
                if deceased:
                    deceased.name = new_name
                    deceased.save()

    # Ensure linked heirs show their registered relationship if it was never set correctly
    gender_map = {'MALE': 'ذكر', 'FEMALE': 'أنثى'}
    rel_map = {'SON': 'ابن', 'DAUGHTER': 'بنت', 'WIFE': 'زوجة', 'HUSBAND': 'زوج', 'FATHER': 'أب', 'MOTHER': 'أم'}
    
    for form in heir_formset:
        if form.instance.user:
            # Sync Gender
            u_gender = form.instance.user.gender
            if u_gender in gender_map: u_gender = gender_map[u_gender]
            if u_gender:
                form.initial['gender'] = u_gender
                if not form.instance.gender or form.instance.gender in ['', 'MALE', 'FEMALE']:
                    form.instance.gender = u_gender
                    form.instance.save()
            
            # Sync Relationship
            u_rel = form.instance.user.relationship_to_deceased
            if u_rel in rel_map: u_rel = rel_map[u_rel]
            if u_rel:
                form.initial['relationship'] = u_rel
                if not form.instance.relationship or form.instance.relationship in ['', 'SON', 'MALE']:
                    form.instance.relationship = u_rel
                    form.instance.save()

    pending_heirs = []
    if deceased and deceased.name and deceased.name not in ['', 'احمدمحمد', 'موقت', 'متوفى']:
        pending_heirs = User.objects.filter(
            role=User.Role.HEIR, 
            deceased_name__icontains=deceased.name,
            heir_records__isnull=True
        )
    else:
        # If deceased name is still default, maybe show heirs who registered recently?
        # Or heirs who match the case number if we had such a field.
        # For now, let's keep it empty until name is saved.
        pass

    return render(request, 'clerks/enter_case_data.html', {
        'case': case,
        'deceased_form': deceased_form,
        'heir_formset': heir_formset,
        'asset_form': AssetForm(),
        'debt_form': DebtForm(),
        'will_form': WillForm(),
        'pending_heirs': pending_heirs
    })
