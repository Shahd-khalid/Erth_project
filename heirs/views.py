from django.shortcuts import render, redirect, get_object_or_404
from cases.models import Case, Heir, Asset, HeirAssetSelection, AssetComponent, SelectionLog, DisputeRaffle, PaymentSettlement
from django.contrib import messages
from django.contrib.auth.decorators import login_required

@login_required
def dashboard(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Handle mutual consent vote from the dashboard
        if action in ['agree_mutual', 'disagree_mutual']:
            heir_id = request.POST.get('heir_id')
            heir = get_object_or_404(Heir, id=heir_id, user=request.user)
            case = heir.case
            
            if action == 'agree_mutual':
                heir.mutual_consent_status = Heir.MutualConsentStatus.AGREED
                heir.save()
                if not case.heirs.exclude(mutual_consent_status=Heir.MutualConsentStatus.AGREED).exists():
                    # All heirs agreed, but now we wait for Judge approval
                    messages.success(request, 'تم إجماع الورثة على التراضي! بانتظار موافقة فضيلة القاضي للانتقال لمرحلة الاختيار.')
                else:
                    messages.success(request, 'تم تسجيل موافقتك. بانتظار تصويت بقية الورثة.')
            elif action == 'disagree_mutual':
                heir.mutual_consent_status = Heir.MutualConsentStatus.DISAGREED
                heir.save()
                case.status = Case.Status.ALTERNATIVE_SELECTION
                case.save()
                messages.warning(request, 'تم رفض القسمة بالتراضي. بدأ مسار الاعتراض.')
                
            return redirect('heirs:dashboard')

        # Handle updating deceased name
        deceased_name = request.POST.get('deceased_name')
        if deceased_name:
            user = request.user
            user.deceased_name = deceased_name
            user.save()
            messages.success(request, 'تم تحديث اسم المتوفى بنجاح.')
            return redirect('heirs:dashboard')

    # Find all heir records associated with this user
    my_heir_records = Heir.objects.filter(user=request.user)
    
    # Pre-fetch objecting heirs and settlements for each case record
    for record in my_heir_records:
        case = record.case
        if case.status == Case.Status.CONSENT_PENDING:
            case.objecting_heirs = case.heirs.filter(acceptance_status=Heir.AcceptanceStatus.REJECTED)
        
        # Settlements
        record.bills = PaymentSettlement.objects.filter(payer=record, is_paid_to_judge=False)
        record.receipts_waiting = PaymentSettlement.objects.filter(original_owner=record, is_paid_to_judge=True, is_delivered_to_owner=False)
        
        # Activity Feed
        case.recent_logs = case.selection_logs.all()[:5]
    
    return render(request, 'heirs/dashboard.html', {
        'my_heir_records': my_heir_records
    })

def session_lobby(request, link):
    case = get_object_or_404(Case, session_link=link, status=Case.Status.SESSION_ACTIVE)
    
    return render(request, 'heirs/lobby.html', {'case': case})

def session_home(request, link, heir_id):
    case = get_object_or_404(Case, session_link=link)
    heir = get_object_or_404(Heir, id=heir_id, case=case)
    
    # Allocated Items
    my_assets = heir.allocated_assets.all()
    my_components = heir.allocated_components.select_related('asset').all()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'accept':
            heir.acceptance_status = Heir.AcceptanceStatus.ACCEPTED
            heir.save()
            messages.success(request, 'تم قبول القسمة بنجاح. شكراً لك.')
            return redirect('heirs:session_home', link=link, heir_id=heir.id)
            
        elif action == 'reject':
            heir.acceptance_status = Heir.AcceptanceStatus.REJECTED
            heir.save()
            
            case.status = Case.Status.CONSENT_PENDING
            case.save()
            
            case.heirs.all().update(mutual_consent_status=Heir.MutualConsentStatus.NOT_VOTED)
            heir.mutual_consent_status = Heir.MutualConsentStatus.AGREED
            heir.save()
            
            messages.success(request, 'تم رفض القسمة وطلب قسمة بالتراضي. تم إشعار بقية الورثة للتصويت.')
            return redirect('heirs:session_home', link=link, heir_id=heir.id)
            
        elif action == 'agree_mutual':
            # Kept here for backward compatibility if ever submitted from session_home
            heir.mutual_consent_status = Heir.MutualConsentStatus.AGREED
            heir.save()
            
            # Check if all heirs agreed
            if not case.heirs.exclude(mutual_consent_status=Heir.MutualConsentStatus.AGREED).exists():
                # Wait for judge approval
                messages.success(request, 'تم إجماع الورثة على التراضي! بانتظار موافقة فضيلة القاضي للانتقال لمرحلة الاختيار.')
            else:
                messages.success(request, 'تم تسجيل موافقتك. بانتظار تصويت بقية الورثة.')
            return redirect('heirs:session_home', link=link, heir_id=heir.id)

        elif action == 'disagree_mutual':
            heir.mutual_consent_status = Heir.MutualConsentStatus.DISAGREED
            heir.save()
            case.status = Case.Status.ALTERNATIVE_SELECTION
            case.save()
            messages.warning(request, 'تم رفض القسمة بالتراضي. بدأ مسار الاعتراض.')
            return redirect('heirs:session_home', link=link, heir_id=heir.id)

    objecting_heirs = case.heirs.filter(acceptance_status=Heir.AcceptanceStatus.REJECTED)
    
    # Activity Feed
    case.recent_logs = case.selection_logs.all()[:8]
    
    # Judge Approval Check
    case.waiting_for_judge_approval = False
    if case.status == Case.Status.CONSENT_PENDING and not case.judge_consents_to_mutual:
        if not case.heirs.exclude(mutual_consent_status=Heir.MutualConsentStatus.AGREED).exists():
            case.waiting_for_judge_approval = True
    
    # Financial Settlements for this specific heir in this case
    my_bills = PaymentSettlement.objects.filter(case=case, payer=heir)
    my_receipts = PaymentSettlement.objects.filter(case=case, original_owner=heir)
    
    # Raffles/Disputes involving this heir that are NOT resolved
    active_disputes = DisputeRaffle.objects.filter(case=case, contenders=heir, is_resolved=False).distinct()
    
    # Raffles/Disputes involving this heir that ARE resolved (to show results)
    resolved_disputes = DisputeRaffle.objects.filter(case=case, contenders=heir, is_resolved=True).distinct()
    
    return render(request, 'heirs/session_home.html', {
        'case': case,
        'heir': heir,
        'my_assets': my_assets,
        'my_components': my_components,
        'objecting_heirs': objecting_heirs,
        'my_bills': my_bills,
        'my_receipts': my_receipts,
        'active_disputes': active_disputes,
        'resolved_disputes': resolved_disputes
    })

def select_assets(request, link, heir_id):
    case = get_object_or_404(Case, session_link=link)
    heir = get_object_or_404(Heir, id=heir_id, case=case)
    
    if case.status not in [Case.Status.MUTUAL_SELECTION, Case.Status.ALTERNATIVE_SELECTION]:
        messages.error(request, 'لا يمكنك اختيار الأصول في هذه المرحلة.')
        return redirect('heirs:session_home', link=link, heir_id=heir.id)
    
    from cases.models import AssetComponent
    available_assets = Asset.objects.filter(case=case)
    available_components = AssetComponent.objects.filter(asset__case=case)
    
    if request.method == 'POST':
        selected_asset_ids = request.POST.getlist('selected_assets')
        selected_component_ids = request.POST.getlist('selected_components')
        confirm_balance = request.POST.get('confirm_balance')
        
        selected_assets = Asset.objects.filter(id__in=selected_asset_ids)
        selected_components = AssetComponent.objects.filter(id__in=selected_component_ids)
        
        total_value = sum(a.value for a in selected_assets) + sum(c.value for c in selected_components)
        share_value = heir.share_value
        
        diff = total_value - share_value
        is_valid = True
        
        if diff > 0 and confirm_balance != 'on':
            is_valid = False
            messages.error(request, f'القيمة المختارة ({total_value}) أكبر من نصيبك. يجب إعطاء تعهد بتوفية الفرق المتبقي ({diff}).')

        if is_valid:
             HeirAssetSelection.objects.filter(heir=heir).delete()
             
             for asset in selected_assets:
                 is_chal = False
                 if case.status == Case.Status.ALTERNATIVE_SELECTION and asset.assigned_to and asset.assigned_to != heir:
                     is_chal = True
                 HeirAssetSelection.objects.create(
                     heir=heir, asset=asset, 
                     requires_pledge=(diff>0), pledge_amount=diff if diff>0 else 0,
                     is_challenging_owner=is_chal
                 )
                 
                 # Log selection
                 SelectionLog.objects.create(
                     case=case, heir=heir, 
                     action_text=f"قام باختيار الأصل: {asset.description} (القيمة: {asset.value})"
                 )
                 
                 if is_chal:
                    messages.warning(request, f'تم إرسال لـ {asset.assigned_to.name} إشعار طلب نزاع وقرعة على {asset.description}.')
                 
             for comp in selected_components:
                 is_chal = False
                 if case.status == Case.Status.ALTERNATIVE_SELECTION and comp.assigned_to and comp.assigned_to != heir:
                     is_chal = True
                 HeirAssetSelection.objects.create(
                     heir=heir, component=comp, 
                     requires_pledge=(diff>0), pledge_amount=diff if diff>0 else 0,
                     is_challenging_owner=is_chal
                 )
                 
                 # Log selection
                 SelectionLog.objects.create(
                     case=case, heir=heir, 
                     action_text=f"قام باختيار العينة: {comp.description} (القيمة: {comp.value}) من أصل {comp.asset.description}"
                 )
                 
                 if is_chal:
                    messages.warning(request, f'تم إرسال لـ {comp.assigned_to.name} إشعار طلب نزاع وقرعة على العينة {comp.description}.')

             heir.acceptance_status = Heir.AcceptanceStatus.ACCEPTED 
             
             if diff > 0:
                 heir.allocation_description = f"تم الاختيار مع الاستعداد بدفع فرق لزيادة الاختيار: {diff}"
             elif diff < 0:
                 heir.allocation_description = f"تم اختيار أصول وعينات ألقيمة من النصيب (الباقي: {abs(diff)})"
             else:
                 heir.allocation_description = "تم اختيار أصول مطابقة للنصيب"
                  
             heir.save()
             
             # Check if all heirs have submitted their selections
             if not case.heirs.exclude(acceptance_status=Heir.AcceptanceStatus.ACCEPTED).exists():
                 case.status = Case.Status.RAFFLE_PHASE
                 case.save()
                 
                 from django.db.models import Count
                 
                 # 1. Handle Mutual Selection Conflicts (Multiple people choosing same thing)
                 if case.judge_consents_to_mutual:
                     # Assets with multiple selections
                     conflicting_assets = HeirAssetSelection.objects.filter(heir__case=case, asset__isnull=False).values('asset').annotate(count=Count('heir')).filter(count__gt=1)
                     for item in conflicting_assets:
                         asset = Asset.objects.get(id=item['asset'])
                         dispute, _ = DisputeRaffle.objects.get_or_create(case=case, asset=asset)
                         for entry in HeirAssetSelection.objects.filter(asset=asset, heir__case=case):
                             dispute.contenders.add(entry.heir)
                     
                     # Components with multiple selections
                     conflicting_comps = HeirAssetSelection.objects.filter(heir__case=case, component__isnull=False).values('component').annotate(count=Count('heir')).filter(count__gt=1)
                     for item in conflicting_comps:
                         comp = AssetComponent.objects.get(id=item['component'])
                         dispute, _ = DisputeRaffle.objects.get_or_create(case=case, component=comp)
                         for entry in HeirAssetSelection.objects.filter(component=comp, heir__case=case):
                             dispute.contenders.add(entry.heir)
             
             messages.success(request, 'تم حفظ خياراتك بنجاح. سنقوم بإبلاغ القاضي والورثة الآخرين لمعالجة التوزيع.')
             return redirect('heirs:session_home', link=link, heir_id=heir.id)
    
    return render(request, 'heirs/select_assets.html', {
        'case': case,
        'heir': heir,
        'available_assets': available_assets,
        'available_components': available_components
    })

@login_required
def final_report(request, case_id, heir_id):
    case = get_object_or_404(Case, id=case_id, status=Case.Status.COMPLETED)
    heir = get_object_or_404(Heir, id=heir_id, case=case, user=request.user)

    # All Heirs Data for the table
    all_heirs = case.heirs.all()
    heir_data = []
    total_estate_value = sum(a.value for a in case.assets.all())
    
    for h in all_heirs:
        assigned_assets = h.allocated_assets.all()
        assigned_components = h.allocated_components.all()
        
        specific_assets_value = sum(a.value for a in assigned_assets)
        specific_components_value = sum(c.value for c in assigned_components)
        
        total_specific_value = specific_assets_value + specific_components_value
        
        pool_allocation = h.allocated_share - total_specific_value
        if pool_allocation < 0: pool_allocation = 0
            
        heir_data.append({
            'heir': h,
            'assets': assigned_assets,
            'components': assigned_components,
            'specific_assets_value': total_specific_value,
            'pool_allocation': pool_allocation,
            'total_allocated': h.allocated_share,
            'diff': h.allocated_share - h.share_value,
            'is_current': h.id == heir.id
        })
        
    my_data = next((d for d in heir_data if d['heir'].id == heir.id), None)
    
    return render(request, 'heirs/final_report.html', {
        'case': case,
        'heir': heir,
        'my_data': my_data,
        'heir_data': heir_data,
        'total_estate_value': total_estate_value,
    })

from cases.models import PublicAssetListing

@login_required
def my_assets_for_sale(request):
    if request.user.role != 'HEIR':
        return redirect('dashboard')
        
    my_components = AssetComponent.objects.filter(assigned_to__user=request.user).select_related('asset', 'asset__case', 'assigned_to', 'listing').order_by('-created_at')
    
    return render(request, 'heirs/my_assets_sale.html', {
        'my_components': my_components
    })

@login_required
def manage_asset_listing(request, component_id):
    if request.user.role != 'HEIR' or request.method != 'POST':
        return redirect('dashboard')
        
    component = get_object_or_404(AssetComponent, id=component_id, assigned_to__user=request.user)
    
    seller_name = request.POST.get('seller_name')
    seller_email = request.POST.get('seller_email')
    seller_phone = request.POST.get('seller_phone')
    price_str = request.POST.get('price', '').replace(',', '.')
    description = request.POST.get('description')
    
    from decimal import Decimal, InvalidOperation
    try:
        final_price = Decimal(price_str) if price_str else component.value
    except (InvalidOperation, ValueError):
        final_price = component.value
        
    final_description = description if description and description.strip() else component.description
    
    listing, created = PublicAssetListing.objects.update_or_create(
        component=component,
        defaults={
            'seller_name': seller_name,
            'seller_email': seller_email,
            'seller_phone': seller_phone,
            'price': final_price,
            'description': final_description,
            'is_active': True
        }
    )
    
    action_text = "إضافة" if created else "تحديث"
    messages.success(request, f'تم {action_text} العرض بنجاح وبات متاحاً في الصفحة الرئيسية.')
    return redirect('heirs:my_assets_for_sale')

@login_required
def reselect_assets(request, link, heir_id):
    case = get_object_or_404(Case, session_link=link)
    heir = get_object_or_404(Heir, id=heir_id, case=case, user=request.user)
    
    # Delete current selections for this heir
    HeirAssetSelection.objects.filter(heir=heir).delete()
    
    # Update status to allow re-selection
    # If they were REJECTED (original objector), keep it so they stay in Alternative flow if needed
    # If they were just voting, reset to PENDING so they can select again
    if heir.acceptance_status == Heir.AcceptanceStatus.ACCEPTED:
        heir.acceptance_status = Heir.AcceptanceStatus.PENDING
        heir.save()
        
    messages.info(request, "تمت إعادة تعيين اختياراتك. يمكنك الآن اختيار العينات من جديد.")
    return redirect('heirs:select_assets', link=link, heir_id=heir.id)

@login_required
def confirm_payment_sent(request, settlement_id):
    if request.user.role != 'HEIR':
        return redirect('users:dashboard')
        
    settlement = get_object_or_404(PaymentSettlement, id=settlement_id, payer__user=request.user)
    
    if request.method == 'POST':
        settlement.heir_confirmed_payment = True # Need to add this field to model
        settlement.save()
        
        # Log action
        SelectionLog.objects.create(
            case=settlement.case,
            heir=settlement.payer,
            action_text=f"قام بتأكيد تحويل المبلغ المستحق ({settlement.amount} ريال) إلى حساب المحكمة/القاضي."
        )
        
        messages.success(request, 'تم إرسال تأكيد السداد للقاضي. سيتم تفعيل ملكية الأصل لك فور تأكيد القاضي للاستلام.')
        
    return redirect('heirs:session_home', link=settlement.case.session_link, heir_id=settlement.payer.id)

@login_required
def confirm_receipt(request, settlement_id):
    if request.user.role != 'HEIR':
        return redirect('users:dashboard')
        
    settlement = get_object_or_404(PaymentSettlement, id=settlement_id, original_owner__user=request.user)
    
    if request.method == 'POST':
        settlement.is_delivered_to_owner = True
        settlement.save()
        
        # Log action
        SelectionLog.objects.create(
            case=settlement.case,
            heir=settlement.original_owner,
            action_text=f"قام بتأكيد استلام المبلغ المستحق ({settlement.amount} ريال) من القاضي."
        )
        
        messages.success(request, f'تم تأكيد استلام المبلغ من فضيلة القاضي {settlement.case.judge.get_full_name()}.')
        
    return redirect('heirs:session_home', link=settlement.case.session_link, heir_id=settlement.original_owner.id)
