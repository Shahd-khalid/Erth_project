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
        pass 

    from .models import PaymentSettlement, AssetComponent

    heirs = case.heirs.all()
    
    # Get warnings from service
    system_warnings = get_allocation_warnings(case)

    heir_stats = []
    all_selected = True
    all_balanced = True

    for heir in heirs:
        intents = HeirAssetSelection.objects.filter(heir=heir)
        intent_value = sum(i.asset.value if i.asset else i.component.value for i in intents)
        
        assigned_assets_val = sum(a.value for a in heir.allocated_assets.all())
        assigned_comps_val = sum(c.value for c in heir.allocated_components.all())
        
        selected_value = intent_value + assigned_assets_val + assigned_comps_val
        diff = selected_value - heir.share_value
        
        has_selected = intents.exists() or heir.allocated_assets.exists() or heir.allocated_components.exists()
        if not has_selected:
            all_selected = False
            
        status_label = "لم يختر بعد"
        if has_selected:
            if case.status in [Case.Status.MUTUAL_SELECTION, Case.Status.ALTERNATIVE_SELECTION, Case.Status.CONSENT_PENDING]:
                status_label = "بانتظار الإغلاق/القرعة"
            elif case.status == Case.Status.RAFFLE_PHASE:
                status_label = "في مرحلة القرعة"
            else:
                if diff > 0:
                    status_label = f"عليه دفع فرق ({diff})"
                elif diff < 0:
                    status_label = f"لم يكمل النصيب (باقي {abs(diff)})"
                else:
                    status_label = "إغلاق سليم"

        heir_stats.append({
            'name': heir.name,
            'share_value': heir.share_value,
            'selected_value': selected_value,
            'diff': diff,
            'status': status_label,
            'obj': heir,
            'intents': intents
        })

    pending_payments = PaymentSettlement.objects.filter(case=case, is_paid_to_judge=False)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'mark_paid':
            payment_id = request.POST.get('payment_id')
            payment = get_object_or_404(PaymentSettlement, id=payment_id, case=case)
            payment.is_paid_to_judge = True
            payment.save()
            
            # Official ownership transfer
            target = payment.asset or payment.component
            if target:
                target.assigned_to = payment.payer
                target.save()
                
                # Update allocated share
                payer = payment.payer
                payer.allocated_share += target.value
                payer.save()
                
                from .models import SelectionLog
                SelectionLog.objects.create(
                    case=case,
                    heir=payment.payer,
                    action_text=f"تم نقل ملكية {target.description} له بشكل رسمي بعد توفية الالتزامات المالية (عبر المراجعة)."
                )

            messages.success(request, f'تم إثبات استلام الدفعة بقيمة {payment.amount} من {payment.payer.name} وتحويل الملكية له.')
            
            # If paid, we need to assign the asset back to them maybe?
            # Actually, start_lottery kept it `assigned_to = None` until paid. Let's just trust it's tracked.
            
            return redirect('review_distribution', case_id=case.id)

        elif action == 'approve':
            if pending_payments.exists():
                messages.error(request, 'لا يمكن اعتماد القسمة لوجود مبالغ معلقة لم يتم تسويتها بعد.')
                return redirect('review_distribution', case_id=case.id)
                
            # 1. Finalize assignments from intents
            for h in heirs:
                intents = HeirAssetSelection.objects.filter(heir=h)
                for intent in intents:
                    if intent.asset:
                        intent.asset.assigned_to = h
                        intent.asset.save()
                        h.allocated_share += intent.asset.value
                    if intent.component:
                        intent.component.assigned_to = h
                        intent.component.save()
                        h.allocated_share += intent.component.value
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
            return redirect('start_lottery', case_id=case.id)

    return render(request, 'cases/review_distribution.html', {
        'case': case,
        'heir_stats': heir_stats,
        'all_selected': all_selected,
        'all_balanced': all_balanced,
        'system_warnings': system_warnings,
        'pending_payments': pending_payments,
    })

import random

@login_required
def start_lottery(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    if request.user != case.judge:
        pass # Security

    from .models import DisputeRaffle, PaymentSettlement, AssetComponent

    # 1. Automatically generate missing disputes if in RAFFLE_PHASE
    if case.status in [Case.Status.RAFFLE_PHASE, Case.Status.PAYMENTS_PHASE]:
        conflicted_assets = Asset.objects.filter(case=case).annotate(
            selection_count=Count('selection_intents')
        ).filter(selection_count__gt=1)
        
        for asset in conflicted_assets:
            dispute, created = DisputeRaffle.objects.get_or_create(case=case, asset=asset)
            if created:
                conflict_heirs = Heir.objects.filter(selections__asset=asset)
                dispute.contenders.set(conflict_heirs)
                
        conflicted_comps = AssetComponent.objects.filter(asset__case=case).annotate(
            selection_count=Count('selection_intents')
        ).filter(selection_count__gt=1)
        
        for comp in conflicted_comps:
            dispute, created = DisputeRaffle.objects.get_or_create(case=case, component=comp)
            if created:
                conflict_heirs = Heir.objects.filter(selections__component=comp)
                dispute.contenders.set(conflict_heirs)
                
        challenges = HeirAssetSelection.objects.filter(heir__case=case, is_challenging_owner=True)
        for chal in challenges:
            if chal.asset:
               dispute, created = DisputeRaffle.objects.get_or_create(case=case, asset=chal.asset)
               if created:
                   dispute.contenders.add(chal.heir)
                   if chal.asset.assigned_to:
                       dispute.contenders.add(chal.asset.assigned_to)
            if chal.component:
               dispute, created = DisputeRaffle.objects.get_or_create(case=case, component=chal.component)
               if created:
                   dispute.contenders.add(chal.heir)
                   if chal.component.assigned_to:
                       dispute.contenders.add(chal.component.assigned_to)

    active_disputes = DisputeRaffle.objects.filter(case=case, is_resolved=False)
    resolved_disputes = DisputeRaffle.objects.filter(case=case, is_resolved=True)
    
    if request.method == 'POST':
        dispute_id = request.POST.get('dispute_id')
        dispute = get_object_or_404(DisputeRaffle, id=dispute_id, case=case)
        
        contenders = list(dispute.contenders.all())
        if contenders:
            winner = random.choice(contenders)
            dispute.winner = winner
            dispute.is_resolved = True
            dispute.save()
            
            target = dispute.asset if dispute.asset else dispute.component
            val = target.value
            old_owner = target.assigned_to
            
            if old_owner and old_owner != winner:
                old_owner.allocated_share -= val
                old_owner.save()
                
            winner_remaining = winner.share_value - winner.allocated_share
            
            if val > winner_remaining:
                diff = val - winner_remaining
                PaymentSettlement.objects.create(
                    case=case, 
                    payer=winner, 
                    original_owner=old_owner if old_owner != winner else None,
                    asset=target if isinstance(target, Asset) else None,
                    component=target if isinstance(target, AssetComponent) else None,
                    amount=diff, 
                    reason=f'دفع فرق لقاء كسب القرعة على {target.description}'
                )
                target.assigned_to = None # Wait for payment
                target.save()
                messages.success(request, f'فاز {winner.name} بقرعة {target.description}، ويتوجب عليه سداد فرق {diff} ريال للقاضي ليتم إدراجها في أملاكه.')
            else:
                target.assigned_to = winner
                target.save()
                winner.allocated_share += val
                winner.save()
                messages.success(request, f'فاز {winner.name} بقرعة {target.description} وحصل عليه فوراً.')
            
            if not DisputeRaffle.objects.filter(case=case, is_resolved=False).exists():
                case.status = Case.Status.PAYMENTS_PHASE
                case.save()
            
        return redirect('start_lottery', case_id=case.id)

    return render(request, 'cases/start_lottery.html', {
        'case': case,
        'active_disputes': active_disputes,
        'resolved_disputes': resolved_disputes
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
