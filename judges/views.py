from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from cases.models import Case, Asset, Debt, Will, Heir, Deceased, HeirAssetSelection, AssetComponent, PaymentSettlement, DisputeRaffle, SelectionLog
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

    # Active Sessions (Open for all phases from active session to payment)
    session_cases = Case.objects.filter(
        judge=request.user,
        status__in=[
            Case.Status.SESSION_ACTIVE,
            Case.Status.CONSENT_PENDING,
            Case.Status.MUTUAL_SELECTION,
            Case.Status.ALTERNATIVE_SELECTION,
            Case.Status.RAFFLE_PHASE,
            Case.Status.PAYMENTS_PHASE
        ]
    )
    # Completed Cases Archive
    completed_cases = Case.objects.filter(
        judge=request.user,
        status=Case.Status.COMPLETED
    ).order_by('-created_at')
    
    # For each session case, check if all heirs agreed but judge hasn't
    for case in session_cases:
        if case.status == Case.Status.CONSENT_PENDING and not case.judge_consents_to_mutual:
            all_agreed = not case.heirs.exclude(mutual_consent_status=Heir.MutualConsentStatus.AGREED).exists()
            case.waiting_for_judge_approval = all_agreed
        else:
            case.waiting_for_judge_approval = False
    
    # My Clerks (Only show approved ones or indicate status)
    # Let's show all assigned, but template can distinguish
    my_clerks = User.objects.filter(role=User.Role.CLERK, assigned_judge=request.user)
    
    pending_settlements = PaymentSettlement.objects.filter(case__judge=request.user, is_paid_to_judge=False)
    waiting_receiver_settlements = PaymentSettlement.objects.filter(case__judge=request.user, is_paid_to_judge=True, is_delivered_to_owner=False)

    return render(request, 'judges/dashboard.html', {
        'new_cases': new_cases, 
        'review_cases': review_cases,
        'session_cases': session_cases,
        'active_cases': active_cases,
        'completed_cases': completed_cases,
        'my_clerks': my_clerks,
        'pending_settlements': pending_settlements,
        'waiting_receiver_settlements': waiting_receiver_settlements
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
             # BLOCK finalization if payments pending
             if PaymentSettlement.objects.filter(case=case, is_delivered_to_owner=False).exists():
                 messages.error(request, "لا يمكن اعتماد القسمة النهائية لوجود تسويات مالية معلقة لم تكتمل دورتها (سداد وتأكيد استلام).")
                 return redirect('judges:allocate_assets', case_id=case.id)
                 
             case.status = Case.Status.SESSION_ACTIVE
             case.save()
             messages.success(request, "تم اعتماد القسمة بنجاح.")
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
                # No excess, assign now
                asset.assigned_to = winner
                asset.save()
                winner.allocated_share += val
                winner.save()
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
            target.assigned_to = settlement.payer
            target.save()
            
            # Update allocated share
            payer = settlement.payer
            payer.allocated_share += target.value
            payer.save()
            
            # Log final ownership
            SelectionLog.objects.create(
                case=settlement.case,
                heir=settlement.payer,
                action_text=f"تم نقل ملكية {target.description} له بشكل رسمي بعد توفية الالتزامات المالية."
            )

        messages.success(request, f'تم إقرار استلام {settlement.amount} من {settlement.payer.name} وتحويل الملكية له بشكل رسمي.')
            
    return redirect('judges:dashboard')
