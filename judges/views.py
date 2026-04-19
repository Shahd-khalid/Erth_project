from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import transaction
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from cases.models import Case, Asset, Debt, Will, Heir, Deceased, HeirAssetSelection, AssetComponent, PaymentSettlement, DisputeRaffle, SelectionLog, EstateObligationAllocation
from cases.forms import AssetForm, DebtForm, WillForm, DeceasedForm
from django.forms import modelformset_factory
from calculator.engine import InheritanceEngine
from cases.services import get_case_judge_completion_status

User = get_user_model()

@login_required
def dashboard(request):
    if request.user.role != 'JUDGE':
        return redirect('dashboard:index')
        
    # 1. New Cases (Awaiting Judge Acceptance)
    new_cases = Case.objects.filter(
        judge=request.user, 
        judge_acceptance_status=Case.JudgeAcceptanceStatus.PENDING
    )
    
    # 2. Foundation Phase (Establishing Case Data)
    foundation_cases = Case.objects.filter(
        judge=request.user,
        judge_acceptance_status=Case.JudgeAcceptanceStatus.ACCEPTED,
        status__in=[Case.Status.ASSIGNED_TO_JUDGE, Case.Status.WITH_CLERK]
    )
    
    # 3. Partition Phase (Ready for Calculation, Sessions, Consents, Raffles)
    partition_cases = Case.objects.filter(
        judge=request.user,
        status__in=[
            Case.Status.DATA_REVIEW,
            Case.Status.READY_FOR_CALCULATION,
            Case.Status.SESSION_ACTIVE,
            Case.Status.CONSENT_PENDING,
            Case.Status.MUTUAL_SELECTION,
            Case.Status.ALTERNATIVE_SELECTION,
            Case.Status.RAFFLE_PHASE
        ]
    )
    
    # 4. Liquidation Phase (Payment Handling)
    liquidation_cases = Case.objects.filter(
        judge=request.user,
        status=Case.Status.PAYMENTS_PHASE
    )

    # 5. Completed Archive
    completed_cases = Case.objects.filter(
        judge=request.user,
        status=Case.Status.COMPLETED
    ).order_by('-created_at')

    # URGENT ACTIONS
    # Urgent: Consent Pending where all heirs agreed
    urgent_approval_cases = []
    for case in partition_cases.filter(status=Case.Status.CONSENT_PENDING):
        all_agreed = not case.heirs.exclude(mutual_consent_status=Heir.MutualConsentStatus.AGREED).exists()
        if all_agreed and not case.judge_consents_to_mutual:
            urgent_approval_cases.append(case)

    # Urgent: Unresolved Raffles
    pending_raffles = DisputeRaffle.objects.filter(case__judge=request.user, is_resolved=False)

    # Urgent: Unconfirmed Payments (paid to judge but not yet processed)
    unconfirmed_payments = PaymentSettlement.objects.filter(case__judge=request.user, is_paid_to_judge=True, is_delivered_to_owner=False)

    # SPECIAL SECTIONS (Requests & Objections)
    # 1. Judge Approval Requests (Cases ready for final sign-off via Consensus path)
    judge_completion_requests = []
    for case in Case.objects.filter(judge=request.user).exclude(status=Case.Status.COMPLETED):
        status = get_case_judge_completion_status(case)
        if status.get('ready'):
            judge_completion_requests.append({
                'case': case,
                'title': f"مراجعة نهائية (إجماع الورثة) - قضية {case.case_number}",
                'heirs_count': status['heirs_count']
            })

    # 2. Mutual Consent / Balancing Cases (At least one heir rejected or hasn't agreed yet)
    # The user specifically requested to use the exact same condition as the "الموازنة بالتراضي" button, 
    # which is captured by the `can_open_mutual_balance` property.
    mutual_consent_cases = []
    for case in partition_cases:
        if case.can_open_mutual_balance:
            mutual_consent_cases.append(case)

    # DATA LOGS & STATS
    latest_logs = SelectionLog.objects.filter(case__judge=request.user).order_by('-created_at')[:10]
    
    active_cases_count = Case.objects.filter(judge=request.user).exclude(status=Case.Status.COMPLETED).count()
    pending_decisions_count = len(urgent_approval_cases) + pending_raffles.count() + unconfirmed_payments.count() + len(judge_completion_requests)
    
    total_estate_value = Asset.objects.filter(case__judge=request.user).aggregate(total=Sum('value'))['total'] or Decimal('0.00')
    collected_amounts = PaymentSettlement.objects.filter(case__judge=request.user, is_paid_to_judge=True).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    my_clerks = User.objects.filter(role='CLERK', assigned_judge=request.user)

    return render(request, 'judges/dashboard.html', {
        'new_cases': new_cases,
        'foundation_cases': foundation_cases,
        'partition_cases': partition_cases,
        'liquidation_cases': liquidation_cases,
        'completed_cases': completed_cases,
        'urgent_approval_cases': urgent_approval_cases,
        'pending_raffles': pending_raffles,
        'unconfirmed_payments': unconfirmed_payments,
        'judge_completion_cases': judge_completion_requests,
        'judge_completion_requests_count': len(judge_completion_requests),
        'mutual_consent_cases': mutual_consent_cases,
        'consent_requests_count': len(mutual_consent_cases),
        'latest_logs': latest_logs,
        'active_cases_count': active_cases_count,
        'pending_decisions_count': pending_decisions_count,
        'total_estate_value': total_estate_value,
        'collected_amounts': collected_amounts,
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
            total_assets = sum(a.value for a in case.assets.all())
            total_debts = sum(d.amount for d in case.debts.all())
            
            if total_debts >= total_assets:
                messages.error(request, "التركة مستغرقة بالدين، لا يمكن إضافة وصية. رصيد الوصية المتاح هو 0.")
            else:
                form = WillForm(request.POST)
                if form.is_valid():
                    net_estate = total_assets - total_debts
                    one_third = net_estate / Decimal('3.0')
                    existing_wills = sum(w.amount for w in case.wills.all())
                    new_will_amount = form.cleaned_data['amount']
                    
                    if existing_wills + new_will_amount > one_third:
                        messages.error(request, f"لا يمكن إضافة هذه الوصية لأن الإجمالي سيتجاوز الثلث الشرعي المسموح به للمتبقي ({one_third:.2f}).")
                    else:
                        will = form.save(commit=False)
                        will.case = case
                        will.save()
                        
        elif action == 'reject_due_to_debt':
            reason = request.POST.get('reason')
            case.judge_acceptance_status = Case.JudgeAcceptanceStatus.REJECTED
            case.rejection_reason = reason
            case.status = Case.Status.PENDING
            case.judge = None # Unassign judge
            case.save()
            messages.success(request, "تم رفض القضية وإعادتها لمسؤول النظام بسبب استغراقها بالدين.")
            return redirect('judges:dashboard')
        
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
                    
                messages.success(request, "تم حفظ بيانات المورث والورثة بنجاح.")


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

    total_assets = sum(a.value for a in case.assets.all())
    total_debts = sum(d.amount for d in case.debts.all())
    total_wills = sum(w.amount for w in case.wills.all())
    net_estate = max(0, total_assets - total_debts)
    wasiyya_limit = (net_estate / Decimal('3.0')).quantize(Decimal("0.01"))
    wasiyya_remaining = max(0, wasiyya_limit - total_wills)

    return render(request, 'judges/case_details.html', {
        'case': case,
        'asset_form': AssetForm(),
        'debt_form': DebtForm(),
        'will_form': WillForm(),
        'deceased_form': deceased_form,
        'heir_formset': heir_formset,
        'total_assets': total_assets,
        'total_debts': total_debts,
        'total_wills': total_wills,
        'net_estate': net_estate,
        'wasiyya_limit': wasiyya_limit,
        'wasiyya_remaining': wasiyya_remaining,
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
    if total_debts > total_assets:
        messages.error(request, "لا يمكن إجراء الحساب: الديون تتجاوز إجمالي التركة. يرجى مراجعة البيانات أو رفض القضية.")
        return redirect('judges:case_details', case_id=case.id)

    net_after_debt = total_assets - total_debts
    
    # Will 1/3 Rule Check
    max_will = net_after_debt / Decimal('3.0')
    effective_wills = min(total_wills, max_will)
    
    net_estate = net_after_debt - effective_wills
        
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
        
        # 1. Decomposition Actions
        if action == 'prepare_split':
            asset_id = request.POST.get('asset_id')
            split_count = int(request.POST.get('count', 0))
            # Pass back to context to show the detail form
            assets = case.assets.prefetch_related('components').all()
            heirs = case.heirs.all()
            return render(request, 'judges/allocate_assets.html', {
                'case': case,
                'assets': assets,
                'heirs': heirs,
                'splitting_asset_id': int(asset_id),
                'split_count': range(split_count),
                'allocation_stage': 'assets',
                'asset_stage_url': reverse('judges:allocate_assets', args=[case.id]),
                'obligations_stage_url': reverse('judges:allocate_obligations', args=[case.id]),
                'heirs_stage_url': reverse('judges:allocate_heirs', args=[case.id]),
            })

        elif action == 'bulk_create_components':
            asset_id = request.POST.get('asset_id')
            descriptions = request.POST.getlist('descriptions[]')
            values = request.POST.getlist('values[]')
            asset = get_object_or_404(Asset, id=asset_id, case=case)

            try:
                total_parts_value = sum(float(v) for v in values if v)
            except ValueError:
                messages.error(request, "القيم المدخلة غير صحيحة.")
                return redirect('judges:allocate_assets', case_id=case_id)

            total_parts_value_rounded = round(total_parts_value, 2)
            asset_value_rounded = round(float(asset.value), 2)
            
            if total_parts_value_rounded != asset_value_rounded:
                if total_parts_value_rounded > asset_value_rounded:
                    messages.error(request, f"خطأ: مجموع العينات ({total_parts_value_rounded}) تجاوزت قيمة الأصل الأصلية ({asset_value_rounded}). الرجاء إنقاص القيم بمقدار {total_parts_value_rounded - asset_value_rounded}.")
                else:
                    messages.error(request, f"خطأ: مجموع العينات ({total_parts_value_rounded}) أقل من قيمة الأصل الأصلية ({asset_value_rounded}). الرجاء زيادة القيم بمقدار {asset_value_rounded - total_parts_value_rounded}.")
                return redirect('judges:allocate_assets', case_id=case_id)
            
            from django.db import transaction
            with transaction.atomic():
                # Clear existing components to prevent duplicates
                asset.components.all().delete()
                
                for desc, val in zip(descriptions, values):
                    if desc and val:
                        AssetComponent.objects.create(
                            asset=asset,
                            description=desc,
                            value=float(val)
                        )
            messages.success(request, f"تم تقسيم {asset.description} بنجاح.")
            return redirect('judges:allocate_assets', case_id=case_id)

        elif action == 'delete_component':
            comp_id = request.POST.get('component_id')
            AssetComponent.objects.filter(id=comp_id, asset__case=case).delete()
            messages.info(request, "تم حذف الجزء بنجاح.")
            return redirect('judges:allocate_assets', case_id=case.id)

        elif action == 'update_component':
            comp_id = request.POST.get('component_id')
            desc = request.POST.get('description')
            new_val_str = request.POST.get('value')
            comp = get_object_or_404(AssetComponent, id=comp_id, asset__case=case)
            asset = comp.asset
            
            try:
                new_val = float(new_val_str) if new_val_str else 0.0
            except ValueError:
                messages.error(request, "القيمة المدخلة للتعديل غير صحيحة.")
                return redirect('judges:allocate_assets', case_id=case.id)
                
            old_val = float(comp.value)
            diff = round(new_val - old_val, 2)
            
            if diff == 0 and desc:
                # Just updating description
                comp.description = desc
                comp.save()
                messages.success(request, f"تم تحديث وصف {comp.description} بنجاح.")
                return redirect('judges:allocate_assets', case_id=case.id)
            elif diff != 0:
                # Value is changing, need to adjust other components to keep sum equals asset.value
                other_comps = AssetComponent.objects.filter(asset=asset).exclude(id=comp.id)
                num_others = other_comps.count()
                
                if num_others == 0:
                    # Can't change value if there are no other components to absorb the difference
                    if round(new_val, 2) != round(float(asset.value), 2):
                        messages.error(request, f"لا يمكن تعديل القيمة لتصبح ({new_val}) لأن العينة الوحيدة يجب أن تساوي قيمة الأصل ({asset.value}).")
                        return redirect('judges:allocate_assets', case_id=case.id)
                else:
                    # Distribute the negative difference (-diff) evenly among other components
                    # Or proportionate to their current values
                    adjustment_per_comp = -diff / num_others
                    
                    from django.db import transaction
                    with transaction.atomic():
                        comp.description = desc if desc else comp.description
                        comp.value = new_val
                        comp.save()
                        
                        for oc in other_comps:
                            # Simple distribution, might result in negative values if diff is huge, handle it
                            new_oc_val = float(oc.value) + adjustment_per_comp
                            if new_oc_val < 0:
                                messages.error(request, f"لا يمكن زيادة العينة ({new_val}) لأنها ستجعل العينات الأخرى سالبة. الرجاء إعادة التقسيم.")
                                return redirect('judges:allocate_assets', case_id=case.id)
                            oc.value = new_oc_val
                            oc.save()

                messages.success(request, f"تم تحديث قيمة {comp.description} وتعديل باقي عينات الأصل تلقائياً للمحافظة على إجمالي القيمة.")
            return redirect('judges:allocate_assets', case_id=case.id)

        # 2. Main Allocation Saving
        elif action == 'save_allocation':
            # Validation Step: Calculate proposed allocation per heir
            proposed_allocations = {}
            for heir in case.heirs.all():
                proposed_allocations[heir.id] = 0.0
            
            # Sum up proposed asset assignments
            for asset in case.assets.all():
                heir_id = request.POST.get(f'asset_{asset.id}')
                if heir_id:
                    proposed_allocations[int(heir_id)] += float(asset.value)
                    
            # Sum up proposed component assignments
            for comp in AssetComponent.objects.filter(asset__case=case):
                heir_id = request.POST.get(f'comp_{comp.id}')
                if heir_id:
                    proposed_allocations[int(heir_id)] += float(comp.value)

            # Check allocations against shares
            has_errors = False
            for heir in case.heirs.all():
                manual_share = request.POST.get(f'value_{heir.id}')
                # Use manual override if provided, else use current share_value
                target_share = float(manual_share) if manual_share else float(heir.share_value)
                proposed_total = round(proposed_allocations[heir.id], 2)
                target_share_rounded = round(target_share, 2)
                
                if proposed_total != target_share_rounded:
                    messages.error(request, f"خطأ في تخصيص الوريث {heir.name}: إجمالي ما تم تخصيصه ({proposed_total}) لا يساوي نصيبه ({target_share_rounded}).")
                    has_errors = True
            
            if has_errors:
                return redirect('judges:allocate_assets', case_id=case.id)

            # --- Validation Passed. Perform Save ---
            
            # Reset existing allocations for this case for a fresh save
            case.assets.all().update(assigned_to=None, is_locked=False)
            AssetComponent.objects.filter(asset__case=case).update(assigned_to=None)
            
            # Save Asset Assignments
            for asset in case.assets.all():
                heir_id = request.POST.get(f'asset_{asset.id}')
                if heir_id:
                    heir = get_object_or_404(Heir, id=heir_id, case=case)
                    asset.assigned_to = heir
                    asset.is_locked = True
                    asset.save()

            # Save Component Assignments
            for comp in AssetComponent.objects.filter(asset__case=case):
                heir_id = request.POST.get(f'comp_{comp.id}')
                if heir_id:
                    heir = get_object_or_404(Heir, id=heir_id, case=case)
                    comp.assigned_to = heir
                    comp.save()
            
            # Update Heir share values and allocated amounts
            for heir in case.heirs.all():
                manual_share = request.POST.get(f'value_{heir.id}')
                desc = request.POST.get(f'desc_{heir.id}')
                
                if manual_share:
                    heir.share_value = manual_share
                if desc:
                    heir.allocation_description = desc
                
                # Calculate current total allocated
                sum_assets = sum(a.value for a in heir.allocated_assets.all())
                sum_comps = sum(c.value for c in heir.allocated_components.all())
                heir.allocated_share = sum_assets + sum_comps
                heir.save()
                
            messages.success(request, "تم حفظ توزيع التركة بنجاح.")
            return redirect('judges:allocate_assets', case_id=case.id)
            
        elif action == 'reset_allocation':
            # Unassign all assets
            case.assets.all().update(assigned_to=None, is_locked=False)
            
            # Unassign all components
            AssetComponent.objects.filter(asset__case=case).update(assigned_to=None)
            
            # Reset allocated share tracking for heirs
            for heir in case.heirs.all():
                heir.allocated_share = 0
                heir.save()
                
            messages.success(request, "تمت إعادة التوزيع بنجاح. جميع الاختيارات ملغاة وأرصدة الورثة عادت كاملة.")
            return redirect('judges:allocate_assets', case_id=case.id)
            
        elif action == 'publish_session':
             if PaymentSettlement.objects.filter(case=case, is_delivered_to_owner=False).exists():
                 messages.error(request, "لا يمكن اعتماد القسمة النهائية لوجود تسويات مالية معلقة لم تكتمل دورتها (سداد وتأكيد استلام).")
                 return redirect('judges:allocate_assets', case_id=case.id)

             # --- SAFETY CHECK: Ensure calculation has been run ---
             for heir in case.heirs.all():
                 if not heir.is_blocked and (heir.share_value is None or heir.share_value <= 0):
                     messages.error(request, f"خطأ: لم يتم تحديد النصيب الشرعي للوريث {heir.name}. يرجى العودة لصفحة الحساب الشرعي واحتساب المواريث أولاً.")
                     return redirect('judges:allocate_assets', case_id=case.id)

             
             # --- AUTO-SAVE & VALIDATE CURRENT SELECTIONS BEFORE PUBLISHING ---
             with transaction.atomic():
                 # 1. Validation Step
                 proposed_allocations = {heir.id: 0.0 for heir in case.heirs.all()}
                 for asset in case.assets.all():
                     heir_id = request.POST.get(f'asset_{asset.id}')
                     if heir_id: proposed_allocations[int(heir_id)] += float(asset.value)
                 for comp in AssetComponent.objects.filter(asset__case=case):
                     heir_id = request.POST.get(f'comp_{comp.id}')
                     if heir_id: proposed_allocations[int(heir_id)] += float(comp.value)

                 has_errors = False
                 for heir in case.heirs.all():
                     target_share = float(request.POST.get(f'value_{heir.id}') or heir.share_value)
                     if round(proposed_allocations[heir.id], 2) != round(target_share, 2):
                         messages.error(request, f"خطأ في تخصيص الوريث {heir.name}: الإجمالي لا يطابق النصيب.")
                         has_errors = True
                 if has_errors: return redirect('judges:allocate_assets', case_id=case.id)

                 # 2. Perform Save
                 case.assets.all().update(assigned_to=None, is_locked=False)
                 AssetComponent.objects.filter(asset__case=case).update(assigned_to=None)
                 
                 for asset in case.assets.all():
                     hid = request.POST.get(f'asset_{asset.id}')
                     if hid:
                         heir = Heir.objects.get(id=hid)
                         asset.assigned_to = heir
                         asset.is_locked = True
                         asset.save()

                 for comp in AssetComponent.objects.filter(asset__case=case):
                     hid = request.POST.get(f'comp_{comp.id}')
                     if hid:
                         comp.assigned_to = Heir.objects.get(id=hid)
                         comp.save()

                 for heir in case.heirs.all():
                     ms = request.POST.get(f'value_{heir.id}'); desc = request.POST.get(f'desc_{heir.id}')
                     if ms: heir.share_value = ms
                     if desc: heir.allocation_description = desc
                     heir.allocated_share = sum(a.value for a in heir.allocated_assets.all()) + sum(c.value for c in heir.allocated_components.all())
                     heir.save()

                 # 3. UNIFIED SELECTION: Populate HeirAssetSelection
                 HeirAssetSelection.objects.filter(heir__case=case).delete()
                 for asset in case.assets.filter(assigned_to__isnull=False):
                     HeirAssetSelection.objects.create(heir=asset.assigned_to, asset=asset, status=HeirAssetSelection.SelectionStatus.PENDING)
                 for comp in AssetComponent.objects.filter(asset__case=case, assigned_to__isnull=False):
                     HeirAssetSelection.objects.create(
                         heir=comp.assigned_to,
                         component=comp,
                         status=HeirAssetSelection.SelectionStatus.PENDING
                     )

             messages.success(request, "تم اعتماد القسمة المبدئية بنجاح بنجاح وتوزيعها على الورثة.")
             return redirect('judges:dashboard')

    # Data for Rendering
    assets = case.assets.prefetch_related('components', 'selection_intents__heir').all()
    heirs = case.heirs.all()
    
    has_pending_payments = PaymentSettlement.objects.filter(case=case, is_delivered_to_owner=False).exists()
    
    return render(request, 'judges/allocate_assets.html', {
        'case': case,
        'assets': assets,
        'heirs': heirs,
        'has_pending_payments': has_pending_payments,
        'allocation_stage': 'assets',
        'asset_stage_url': reverse('judges:allocate_assets', args=[case.id]),
        'obligations_stage_url': reverse('judges:allocate_obligations', args=[case.id]),
        'heirs_stage_url': reverse('judges:allocate_heirs', args=[case.id]),
    })

@login_required
def approve_mutual_consent(request, case_id):
    if request.user.role != 'JUDGE':
        return redirect('dashboard')
        
    case = get_object_or_404(Case, id=case_id, judge=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            case.judge_consents_to_mutual = True
            case.status = Case.Status.MUTUAL_SELECTION
            case.save()
            
            # --- DEFINITIVE CLEANUP ---
            case.assets.all().update(assigned_to=None, is_locked=False)
            AssetComponent.objects.filter(asset__case=case).update(assigned_to=None)
            for h in case.heirs.all():
                h.allocated_share = 0
                h.save()
            HeirAssetSelection.objects.filter(heir__case=case).delete()
            SelectionLog.objects.filter(case=case).delete()
            # ---------------------------
            
            messages.success(request, 'تمت الموافقة على القسمة بالتراضي وتصفير التوزيع السابق. يمكن للورثة الآن البدء باختيار الأصول.')
        else:
            case.status = Case.Status.ALTERNATIVE_SELECTION
            case.save()
            messages.warning(request, 'تم رفض القسمة بالتراضي. سيتم الانتقال لمسار النزاعات والاعتراضات.')
            
    return redirect('judges:dashboard')

@login_required
def resolve_raffle(request, dispute_id):
    if request.user.role != 'JUDGE':
        return redirect('dashboard')
        
    dispute = get_object_or_404(DisputeRaffle, id=dispute_id, case__judge=request.user)
    
    if request.method == 'POST':
        import random
        contenders = list(dispute.contenders.all())
        if contenders:
            winner = random.choice(contenders)
            dispute.winner = winner
            dispute.is_resolved = True
            dispute.save()
            
            # Check financial impact
            asset = dispute.asset or dispute.component
            val = asset.value
            
            current_total = winner.allocated_share
            total_after_win = current_total + val
            
            if total_after_win > winner.share_value:
                # Excess value detected
                diff = total_after_win - winner.share_value
                from cases.models import PaymentSettlement
                
                original_owner = asset.assigned_to
                
                PaymentSettlement.objects.create(
                    case=dispute.case,
                    payer=winner,
                    original_owner=original_owner,
                    asset=dispute.asset,
                    component=dispute.component,
                    amount=diff,
                    reason=f"فرق قيمة للحصول على {asset.description} عبر القرعة"
                )
                
                dispute.case.status = Case.Status.PAYMENTS_PHASE
                dispute.case.save()
                messages.warning(request, f'فاز {winner.name} بالقرعة! نظراً لتجاوز نصيبه، عليه سداد {diff} ريال.')
            else:
                # --- SURGICAL SHARE & SELECTION UPDATE (FIX DOUBLE COUNTING) ---
                previous_owner = asset.assigned_to
                
                if winner != previous_owner:
                    # 1. Decrement from previous owner (if any)
                    if previous_owner:
                        previous_owner.allocated_share -= val
                        previous_owner.save()
                        # Delete selection record for loser
                        if dispute.component:
                            HeirAssetSelection.objects.filter(heir=previous_owner, component=dispute.component).delete()
                        else:
                            HeirAssetSelection.objects.filter(heir=previous_owner, asset=dispute.asset).delete()

                    # 2. Increment for winner
                    winner.allocated_share += val
                    winner.save()
                    
                    # 3. Transfer/Create selection record for winner
                    if dispute.component:
                        HeirAssetSelection.objects.get_or_create(
                            heir=winner, component=dispute.component,
                            defaults={'status': HeirAssetSelection.SelectionStatus.ACCEPTED}
                        )
                    else:
                        HeirAssetSelection.objects.get_or_create(
                            heir=winner, asset=dispute.asset,
                            defaults={'status': HeirAssetSelection.SelectionStatus.ACCEPTED}
                        )
                else:
                    # Winner was already the owner, no share change needed (Prevents Double Count)
                    # Just ensure selection record exists
                    if dispute.component:
                        HeirAssetSelection.objects.get_or_create(heir=winner, component=dispute.component, defaults={'status': HeirAssetSelection.SelectionStatus.ACCEPTED})
                    else:
                        HeirAssetSelection.objects.get_or_create(heir=winner, asset=dispute.asset, defaults={'status': HeirAssetSelection.SelectionStatus.ACCEPTED})

                # 4. Final official assignment
                asset.assigned_to = winner
                asset.save()
                messages.success(request, f'فاز {winner.name} بالقرعة وتم تحويل الملكية له.')
            
            # --- New: Formal Result Log ---
            SelectionLog.objects.create(
                case=dispute.case,
                heir=winner,
                action_text=f"فاز بالقرعة الإلكترونية على {asset.description}."
            )
            # ------------------------------
        
    return redirect('judges:dashboard')

@login_required
def confirm_payment(request, settlement_id):
    if request.user.role != 'JUDGE':
        return redirect('dashboard')
        
    settlement = get_object_or_404(PaymentSettlement, id=settlement_id, case__judge=request.user)
    
    if request.method == 'POST':
        settlement.is_paid_to_judge = True
        settlement.save()
        
        # New: Official ownership transfer happens here if it was a raffle winner
        target = settlement.asset or settlement.component
        if target:
            # --- SURGICAL SHARE & SELECTION UPDATE (FIX DOUBLE COUNTING) ---
            previous_owner = target.assigned_to
            payer = settlement.payer
            
            if payer != previous_owner:
                # 1. Decrement from original owner
                if previous_owner:
                    previous_owner.allocated_share -= target.value
                    previous_owner.save()
                    # Delete selection for original owner (loser of dispute)
                    if settlement.component:
                        HeirAssetSelection.objects.filter(heir=previous_owner, component=settlement.component).delete()
                    else:
                        HeirAssetSelection.objects.filter(heir=previous_owner, asset=settlement.asset).delete()

                # 2. Increment for payer
                payer.allocated_share += target.value
                payer.save()
                
                # 3. Transfer/Create selection for payer (new owner)
                if settlement.component:
                    HeirAssetSelection.objects.get_or_create(
                        heir=payer, component=settlement.component,
                        defaults={'status': HeirAssetSelection.SelectionStatus.ACCEPTED}
                    )
                else:
                    HeirAssetSelection.objects.get_or_create(
                        heir=payer, asset=settlement.asset,
                        defaults={'status': HeirAssetSelection.SelectionStatus.ACCEPTED}
                    )
            
            # 4. Final assignment
            target.assigned_to = payer
            target.save()
            
            # Log final ownership
            SelectionLog.objects.create(
                case=settlement.case,
                heir=settlement.payer,
                action_text=f"تم نقل ملكية {target.description} له بشكل رسمي بعد توفية الالتزامات المالية."
            )

        messages.success(request, f'تم إقرار استلام {settlement.amount} من {settlement.payer.name} وتحويل الملكية له بشكل رسمي.')
            
    return render(request, 'judges/dashboard.html')

def _allocate_case_stage(request, case_id, stage='assets'):
    case = get_object_or_404(Case, id=case_id, judge=request.user)
    
    # Common helper for available assets and parts
    targets = []
    
    # 1. Assets (Only those that haven't been split)
    for asset in case.assets.filter(components__isnull=True):
        targets.append({
            'kind': 'asset',
            'id': asset.id,
            'key': f'asset_{asset.id}',
            'label': asset.description,
            'gross_value': asset.value,
            'assigned_to': asset.assigned_to,
            'obligation_total': 0 # To be filled by stage
        })
        
    # 2. Components
    for comp in AssetComponent.objects.filter(asset__case=case):
        targets.append({
            'kind': 'component',
            'id': comp.id,
            'key': f'comp_{comp.id}',
            'label': comp.description,
            'parent_label': comp.asset.description,
            'gross_value': comp.value,
            'assigned_to': comp.assigned_to,
            'obligation_total': 0
        })
        
    return case, targets

@login_required
def allocate_obligations(request, case_id):
    if request.user.role != 'JUDGE':
        return redirect('dashboard')
        
    case, targets = _allocate_case_stage(request, case_id, stage='obligations')
    process_type = request.GET.get('process_type') # debt or will
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_obligation_allocations':
            # Reset existing obligation allocations for this case
            EstateObligationAllocation.objects.filter(case=case).delete()
            
            # Process radio buttons: target_{key} => value={debt|will}_{id}
            for key, val in request.POST.items():
                if key.startswith('target_'):
                    parts = key.split('_')
                    t_kind = parts[1] # asset or comp
                    t_id = parts[2]
                    
                    v_parts = val.split('_')
                    obj_kind = v_parts[0] # debt or will
                    obj_id = v_parts[1]
                    
                    if t_kind == 'asset':
                        target_asset = get_object_or_404(Asset, id=t_id, case=case)
                        target_comp = None
                        amount = target_asset.value
                    else:
                        target_comp = get_object_or_404(AssetComponent, id=t_id, asset__case=case)
                        target_asset = None
                        amount = target_comp.value
                        
                    if obj_kind == 'debt':
                        debt_obj = get_object_or_404(Debt, id=obj_id, case=case)
                        will_obj = None
                    else:
                        will_obj = get_object_or_404(Will, id=obj_id, case=case)
                        debt_obj = None
                        
                    EstateObligationAllocation.objects.create(
                        case=case,
                        debt=debt_obj,
                        will_entry=will_obj,
                        asset=target_asset,
                        component=target_comp,
                        allocated_amount=amount
                    )
                    
            messages.success(request, "تم حفظ تخصيصات الديون والوصايا بنجاح.")
            return redirect('judges:allocate_obligations', case_id=case.id)

    # Prepare status map
    status_map = {}
    
    # Fetch all debts and wills
    debts = case.debts.all()
    wills = case.wills.all()
    
    for debt in debts:
        alloc_val = debt.allocated_amount
        status_map[f'debt_{debt.id}'] = {
            'obj': debt,
            'kind': 'debt',
            'label': debt.description,
            'amount': debt.amount,
            'allocated': alloc_val,
            'remaining': debt.remaining_amount,
            'is_settled': debt.is_settled,
            'allocations': list(debt.obligation_allocations.all())
        }
        
    for will in wills:
        alloc_val = will.allocated_amount
        status_map[f'will_{will.id}'] = {
            'obj': will,
            'kind': 'will',
            'label': will.description,
            'amount': will.amount,
            'allocated': alloc_val,
            'remaining': will.remaining_amount,
            'is_settled': will.is_settled,
            'allocations': list(will.obligation_allocations.all())
        }

    # Filter targets for display
    display_targets = targets
    for t in display_targets:
        if t['kind'] == 'asset':
            obj = Asset.objects.get(id=t['id'])
        else:
            obj = AssetComponent.objects.get(id=t['id'])
        t['obligation_total'] = obj.obligation_total

    return render(request, 'judges/allocate_obligations.html', {
        'case': case,
        'obligation_status': status_map,
        'obligation_targets': display_targets,
        'allocation_stage': 'obligations',
        'heirs': case.heirs.all(),
        'assets': case.assets.all(),
        'asset_stage_url': reverse('judges:allocate_assets', args=[case.id]),
        'obligations_stage_url': reverse('judges:allocate_obligations', args=[case.id]),
        'heirs_stage_url': reverse('judges:allocate_heirs', args=[case.id]),
        'can_open_heirs_stage': all(d.is_settled for d in debts) and all(w.is_settled for w in wills)
    })

@login_required
def allocate_heirs(request, case_id):
    if request.user.role != 'JUDGE':
        return redirect('dashboard')
        
    case, targets = _allocate_case_stage(request, case_id, stage='heirs')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_allocation':
            # 1. Validation Step: Ensure allocations match shares
            proposed_allocations = {heir.id: 0.0 for heir in case.heirs.all()}
            res_ass_ids = case.obligation_allocations.filter(asset__isnull=False).values_list('asset_id', flat=True)
            res_cmp_ids = case.obligation_allocations.filter(component__isnull=False).values_list('component_id', flat=True)

            for key, val in request.POST.items():
                if val:
                    if key.startswith('asset_'):
                        a_id = key.replace('asset_', '')
                        if int(a_id) not in res_ass_ids:
                             asset_obj = Asset.objects.get(id=a_id)
                             proposed_allocations[int(val)] += float(asset_obj.value)
                    elif key.startswith('comp_'):
                        c_id = key.replace('comp_', '')
                        if int(c_id) not in res_cmp_ids:
                             comp_obj = AssetComponent.objects.get(id=c_id)
                             proposed_allocations[int(val)] += float(comp_obj.value)

            has_errors = False
            for heir in case.heirs.all():
                m_share = request.POST.get(f'value_{heir.id}')
                target_share = float(m_share) if m_share else float(heir.share_value)
                if round(proposed_allocations[heir.id], 2) != round(target_share, 2):
                    messages.error(request, f"خطأ في تخصيص الوريث {heir.name}: إجمالي ما تم تخصيصه للوريث ({round(proposed_allocations[heir.id], 2)}) لا يساوي نصيبه الشرعي ({round(target_share, 2)}).")
                    has_errors = True

            if has_errors:
                return redirect('judges:allocate_heirs', case_id=case.id)

            # 2. Validation Passed. Perform Save ---
            # (Keeping existing save logic below, properly indented)
            case.assets.exclude(id__in=res_ass_ids).update(assigned_to=None)
            AssetComponent.objects.filter(asset__case=case).exclude(id__in=res_cmp_ids).update(assigned_to=None)
            
            # Save new assignments
            for key, val in request.POST.items():
                if val:
                    if key.startswith('asset_'):
                        a_id = key.replace('asset_', '')
                        Asset.objects.filter(id=a_id, case=case).exclude(id__in=res_ass_ids).update(assigned_to_id=val)
                    elif key.startswith('comp_'):
                        c_id = key.replace('comp_', '')
                        AssetComponent.objects.filter(id=c_id).exclude(id__in=res_cmp_ids).update(assigned_to_id=val)

            # Update Heir shares and notes
            for heir in case.heirs.all():
                m_share = request.POST.get(f'value_{heir.id}')
                m_desc = request.POST.get(f'desc_{heir.id}')
                if m_share:
                    heir.share_value = Decimal(str(m_share))
                if m_desc:
                    heir.allocation_description = m_desc
                
                sum_a = heir.allocated_assets.aggregate(t=Sum('value'))['t'] or Decimal('0')
                sum_c = heir.allocated_components.aggregate(t=Sum('value'))['t'] or Decimal('0')
                heir.allocated_share = sum_a + sum_c
                heir.save()

            messages.success(request, "تم حفظ تخصيصات الورثة بنجاح.")
            return redirect('judges:allocate_heirs', case_id=case.id)

        elif action == 'reset_allocation':
            res_ass_ids = case.obligation_allocations.filter(asset__isnull=False).values_list('asset_id', flat=True)
            res_cmp_ids = case.obligation_allocations.filter(component__isnull=False).values_list('component_id', flat=True)
            case.assets.exclude(id__in=res_ass_ids).update(assigned_to=None)
            AssetComponent.objects.filter(asset__case=case).exclude(id__in=res_cmp_ids).update(assigned_to=None)
            case.heirs.all().update(allocated_share=0)
            messages.success(request, "تمت إعادة تعيين التوزيعات بنجاح.")
            return redirect('judges:allocate_heirs', case_id=case.id)

        elif action == 'publish_session':
            if PaymentSettlement.objects.filter(case=case, is_delivered_to_owner=False).exists():
                messages.error(request, "لا يمكن الاعتماد لوجود مبالغ معلقة لم تكتمل دورتها.")
                return redirect('judges:allocate_heirs', case_id=case.id)
            
            # --- AUTO-SAVE & VALIDATE CURRENT SELECTIONS BEFORE PUBLISHING ---
            with transaction.atomic():
                # 0. Validation Step: Ensure allocations match shares
                proposed_allocations = {heir.id: 0.0 for heir in case.heirs.all()}
                res_ass_ids = case.obligation_allocations.filter(asset__isnull=False).values_list('asset_id', flat=True)
                res_cmp_ids = case.obligation_allocations.filter(component__isnull=False).values_list('component_id', flat=True)

                for key, val in request.POST.items():
                    if val:
                        if key.startswith('asset_'):
                            a_id = key.replace('asset_', '')
                            if int(a_id) not in res_ass_ids:
                                 asset_obj = Asset.objects.get(id=a_id)
                                 proposed_allocations[int(val)] += float(asset_obj.value)
                        elif key.startswith('comp_'):
                            c_id = key.replace('comp_', '')
                            if int(c_id) not in res_cmp_ids:
                                 comp_obj = AssetComponent.objects.get(id=c_id)
                                 proposed_allocations[int(val)] += float(comp_obj.value)

                has_errors = False
                for heir in case.heirs.all():
                    m_share = request.POST.get(f'value_{heir.id}')
                    target_share = float(m_share) if m_share else float(heir.share_value)
                    
                    if not heir.is_blocked and (target_share <= 0):
                         messages.error(request, f"خطأ في بيانات الوريث {heir.name}: النصيب الشرعي غير محتسب.")
                         has_errors = True
                    
                    if round(proposed_allocations[heir.id], 2) != round(target_share, 2):
                        messages.error(request, f"خطأ في تخصيص الوريث {heir.name}: إجمالي ما تم تخصيصه ({round(proposed_allocations[heir.id], 2)}) لا يساوي نصيبه الشرعي ({round(target_share, 2)}).")
                        has_errors = True

                if has_errors:
                    transaction.set_rollback(True)
                    return redirect('judges:allocate_heirs', case_id=case.id)

                # 1. Clear existing assignments (unburdened by obligations)
                res_ass_ids = case.obligation_allocations.filter(asset__isnull=False).values_list('asset_id', flat=True)
                res_cmp_ids = case.obligation_allocations.filter(component__isnull=False).values_list('component_id', flat=True)
                case.assets.exclude(id__in=res_ass_ids).update(assigned_to=None)
                AssetComponent.objects.filter(asset__case=case).exclude(id__in=res_cmp_ids).update(assigned_to=None)
                
                # 2. Save new assignments from POST
                for key, val in request.POST.items():
                    if val:
                        if key.startswith('asset_'):
                            a_id = key.replace('asset_', '')
                            Asset.objects.filter(id=a_id, case=case).exclude(id__in=res_ass_ids).update(assigned_to_id=val)
                        elif key.startswith('comp_'):
                            c_id = key.replace('comp_', '')
                            AssetComponent.objects.filter(id=c_id).exclude(id__in=res_cmp_ids).update(assigned_to_id=val)
                
                # 3. Update Heir shares/notes and calculate allocated_share
                for heir in case.heirs.all():
                    m_share = request.POST.get(f'value_{heir.id}')
                    m_desc = request.POST.get(f'desc_{heir.id}')
                    if m_share and m_share.strip():
                        try:
                            heir.share_value = Decimal(str(m_share))
                        except: pass # Keep old value on error
                    if m_desc:
                        heir.allocation_description = m_desc
                    
                    # --- SAFETY CHECK: Don't allow publishing with zero share ---
                    if not heir.is_blocked and (heir.share_value is None or heir.share_value <= 0):
                         messages.error(request, f"خطأ في بيانات الوريث {heir.name}: النصيب الشرعي يساوي صفر. يرجى التأكد من الضغط على زر احتساب المواريث في الصفحة المخصصة.")
                         transaction.set_rollback(True) # Abort the whole publication
                         return redirect('judges:allocate_heirs', case_id=case.id)

                    sum_a = heir.allocated_assets.aggregate(t=Sum('value'))['t'] or Decimal('0')
                    sum_c = heir.allocated_components.aggregate(t=Sum('value'))['t'] or Decimal('0')
                    heir.allocated_share = sum_a + sum_c
                    heir.save()

                # 4. UNIFIED SELECTION: Populate HeirAssetSelection
                HeirAssetSelection.objects.filter(heir__case=case).delete()
                
                # Create for assets
                for asset in case.assets.filter(assigned_to__isnull=False):
                    HeirAssetSelection.objects.create(
                        heir=asset.assigned_to,
                        asset=asset,
                        status=HeirAssetSelection.SelectionStatus.PENDING
                    )
                # Create for components
                for comp in AssetComponent.objects.filter(asset__case=case, assigned_to__isnull=False):
                    HeirAssetSelection.objects.create(
                        heir=comp.assigned_to,
                        component=comp,
                        status=HeirAssetSelection.SelectionStatus.PENDING
                    )

                # 5. Formalize publication
                case.status = Case.Status.SESSION_ACTIVE
                case.save()

            messages.success(request, "تم حفظ التعديلات واعتماد القسمة النهائية بنجاح وتوزيعها على الورثة.")
            return redirect('judges:dashboard')

    # Context Data
    heir_data = []
    total_allocated_all = 0
    for heir in case.heirs.all():
        total_allocated_all += heir.allocated_share
        heir_data.append({
            'id': heir.id,
            'name': heir.name,
            'relationship': heir.get_relationship_display(),
            'share_value': heir.share_value,
            'allocated': heir.allocated_share,
            'description': heir.allocation_description or ""
        })

    # --- ORIGINAL PROJECT LOGIC FOR FILTERING AVAILABLE ITEMS ---
    reserved_asset_ids = case.obligation_allocations.filter(asset__isnull=False).values_list('asset_id', flat=True)
    reserved_comp_ids = case.obligation_allocations.filter(component__isnull=False).values_list('component_id', flat=True)

    # Assets must not be split (components__isnull=True) and not reserved for obligations
    available_assets = case.assets.filter(components__isnull=True).exclude(id__in=reserved_asset_ids)
    
    # Components must not be reserved for obligations
    available_components = AssetComponent.objects.filter(asset__case=case).exclude(id__in=reserved_comp_ids)

    # Calculate Distribution Summary for Dashboard Cards
    all_assets_val = case.assets.aggregate(total=Sum('value'))['total'] or Decimal('0.00')
    
    res_ass_val = case.assets.filter(id__in=reserved_asset_ids).aggregate(total=Sum('value'))['total'] or Decimal('0.00')
    res_cmp_val = AssetComponent.objects.filter(id__in=reserved_comp_ids).aggregate(total=Sum('value'))['total'] or Decimal('0.00')
    
    distribution_summary = {
        'available_count': available_assets.count() + available_components.count(),
        'available_value': (available_assets.aggregate(total=Sum('value'))['total'] or Decimal('0.00')) + \
                          (available_components.aggregate(total=Sum('value'))['total'] or Decimal('0.00')),
        'reserved_count': len(reserved_asset_ids) + len(reserved_comp_ids),
        'reserved_value': res_ass_val + res_cmp_val
    }

    has_pending_payments = PaymentSettlement.objects.filter(case=case, is_delivered_to_owner=False).exists()

    total_estate_value = sum(a.value for a in case.assets.all())

    return render(request, 'judges/allocate_heirs.html', {
        'case': case,
        'heir_data': heir_data,
        'total_estate_value': total_estate_value,
        'total_allocated_all': total_allocated_all,
        'total_remaining_estate': total_estate_value - total_allocated_all,
        'available_assets': available_assets,
        'available_components': available_components,
        'distribution_summary': distribution_summary,
        'has_pending_payments': has_pending_payments,
        'allocation_stage': 'heirs',
        'heirs': case.heirs.all(),
        'assets': case.assets.all(),
        'asset_stage_url': reverse('judges:allocate_assets', args=[case.id]),
        'obligations_stage_url': reverse('judges:allocate_obligations', args=[case.id]),
        'heirs_stage_url': reverse('judges:allocate_heirs', args=[case.id]),
        'can_open_finalize': True
    })

@login_required
def finalize_case_distribution_request(request, case_id):
    case = get_object_or_404(Case, id=case_id, judge=request.user)
    if request.method == 'POST':
        case.status = Case.Status.COMPLETED
        case.save()
        messages.success(request, "تم إغلاق القضية واعتماد التوزيع النهائي بنجاح.")
    return redirect('judges:dashboard')

@login_required
def report_print_view(request):
    cases = Case.objects.filter(judge=request.user)
    total_cases = cases.count()
    active_cases = cases.exclude(status=Case.Status.COMPLETED).count()
    completed_cases = cases.filter(status=Case.Status.COMPLETED).count()
    total_value = sum(sum(a.value for a in c.assets.all()) for c in cases)
    
    from django.utils import timezone
    return render(request, 'judges/report_print.html', {
        'cases': cases,
        'total_cases': total_cases,
        'active_cases': active_cases,
        'completed_cases': completed_cases,
        'total_value': total_value,
        'date': timezone.now()
    })
