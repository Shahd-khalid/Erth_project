import json
import random
from enum import StrEnum
from decimal import Decimal
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Case, Heir, Asset, AssetComponent, HeirAssetSelection, DisputeRaffle, ComponentConflictRequest, SelectionLog, PaymentSettlement, CaseAuditLog, AllocationProposal, Debt, Will, EstateObligationAllocation
from django.db import transaction
from django.db.models import Count, Q, Sum, F
from .forms import CaseForm, DeceasedForm
from .services import auto_allocate, finalize_case_distribution, get_allocation_warnings, are_case_obligations_settled, get_case_judge_completion_status, get_case_obligation_status, get_target_effective_value, get_obligation_target_catalog
from django.views.decorators.http import require_POST
from django.urls import reverse
from urllib.parse import urlencode


REVIEW_SECTION_LABELS = {
    "obligations": "الديون والوصايا",
    "overview": "نظرة عامة",
    "call": "الاتصال الجماعي",
    "heirs": "طلبات الورثة",
    "approvals": "التوزيع المعتمد",
    "settlements": "التسويات المالية",
    "disputes": "النزاعات والقرعة",
    "manual": "التخصيص اليدوي",
    "decision": "القرار النهائي",
}


def _with_querystring(url, **params):
    cleaned_params = {key: value for key, value in params.items() if value not in (None, '')}
    if not cleaned_params:
        return url
    return f"{url}?{urlencode(cleaned_params)}"


class AllocationProcessType(StrEnum):
    HEIR = "heir"
    DEBT = "debt"
    WILL = "will"


def _normalize_allocation_process_type(raw_value):
    try:
        return AllocationProcessType(raw_value or AllocationProcessType.HEIR)
    except ValueError:
        return AllocationProcessType.HEIR


def _build_allocate_share_url(case_id, share_id, process_type=AllocationProcessType.HEIR):
    return _with_querystring(
        reverse('cases:allocate_share', kwargs={'case_id': case_id, 'heir_id': share_id}),
        process_type=str(process_type),
    )


def _get_allocation_subject(case, share_id, process_type):
    if process_type == AllocationProcessType.DEBT:
        return get_object_or_404(Debt, id=share_id, case=case)
    if process_type == AllocationProcessType.WILL:
        return get_object_or_404(Will, id=share_id, case=case)
    return get_object_or_404(Heir, id=share_id, case=case)


def _get_available_obligation_targets(case, obligation):
    target_catalog = get_obligation_target_catalog(case)
    current_allocations = obligation.obligation_allocations.select_related('asset', 'component')
    current_asset_ids = {allocation.asset_id for allocation in current_allocations if allocation.asset_id}
    current_component_ids = {allocation.component_id for allocation in current_allocations if allocation.component_id}

    other_allocations = case.obligation_allocations.all()
    if isinstance(obligation, Debt):
        other_allocations = other_allocations.exclude(debt=obligation)
    else:
        other_allocations = other_allocations.exclude(will_entry=obligation)

    reserved_asset_ids = set(other_allocations.filter(asset__isnull=False).values_list('asset_id', flat=True))
    reserved_component_ids = set(other_allocations.filter(component__isnull=False).values_list('component_id', flat=True))

    available_assets = []
    available_components = []
    for target in target_catalog:
        if target['kind'] == 'asset':
            if getattr(target['obj'], 'assigned_to_id', None):
                continue
            if target['id'] in reserved_asset_ids and target['id'] not in current_asset_ids:
                continue
            available_assets.append(target['obj'])
        else:
            if getattr(target['obj'], 'assigned_to_id', None) or getattr(target['obj'].asset, 'assigned_to_id', None):
                continue
            if target['id'] in reserved_component_ids and target['id'] not in current_component_ids:
                continue
            available_components.append(target['obj'])

    return available_assets, available_components

@login_required
def case_list(request):
    if request.user.role == 'JUDGE':
        cases = Case.objects.filter(judge=request.user)
    else:
        cases = Case.objects.none()
    return render(request, 'cases/case_list.html', {'cases': cases})

@login_required
def create_case(request):
    if request.user.role != 'JUDGE':
        return redirect('users:dashboard')
        
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
            
            CaseAuditLog.objects.create(
                case=case,
                action=CaseAuditLog.ActionType.CASE_OPENED,
                description=f"تم فتح القضية وإضافة بيانات المتوفى: {deceased.name}",
                user=request.user
            )
            return redirect('cases:case_list')
    else:
        case_form = CaseForm()
        deceased_form = DeceasedForm()
    
    return render(request, 'cases/create_case.html', {'case_form': case_form, 'deceased_form': deceased_form})

def reconcile_case_disputes(case):
    def _has_pending_individual_conflict(*, asset=None, component=None):
        pending_conflicts = ComponentConflictRequest.objects.filter(
            case=case,
            triggered_by_individual_rejection=True,
            status=ComponentConflictRequest.Status.PENDING,
        )
        if component is not None:
            return pending_conflicts.filter(component=component).exists()
        if asset is not None:
            return pending_conflicts.filter(parent_asset=asset, is_full_asset=True).exists()
        return False

    # 1. Assets
    for asset in Asset.objects.filter(case=case):
        selected_heir_ids = set(HeirAssetSelection.objects.filter(asset=asset).values_list('heir_id', flat=True))
        if asset.assigned_to_id: selected_heir_ids.add(asset.assigned_to_id)
        if _has_pending_individual_conflict(asset=asset):
            DisputeRaffle.objects.filter(case=case, asset=asset, is_resolved=False).delete()
            continue
        if len(selected_heir_ids) > 1:
            dispute, created = DisputeRaffle.objects.get_or_create(case=case, asset=asset, is_resolved=False)
            dispute.contenders.set(list(selected_heir_ids))
        else:
            DisputeRaffle.objects.filter(case=case, asset=asset, is_resolved=False).delete()
            
    # 2. Components
    for comp in AssetComponent.objects.filter(asset__case=case):
        h_ids_direct = set(HeirAssetSelection.objects.filter(component=comp).values_list('heir_id', flat=True))
        h_ids_parent = set(HeirAssetSelection.objects.filter(asset=comp.asset).values_list('heir_id', flat=True))
        contenders_ids = h_ids_direct | h_ids_parent

        if comp.assigned_to_id: contenders_ids.add(comp.assigned_to_id)
        if comp.asset.assigned_to_id: contenders_ids.add(comp.asset.assigned_to_id)

        if _has_pending_individual_conflict(component=comp):
            DisputeRaffle.objects.filter(case=case, component=comp, is_resolved=False).delete()
            continue
        
        if len(contenders_ids) > 1:
            if ComponentConflictRequest.objects.filter(component=comp, status='ACCEPTED').exists() and len(contenders_ids) == 1:
                 # This check handles the case where only one person is left after ceding
                 DisputeRaffle.objects.filter(case=case, component=comp, is_resolved=False).delete()
                 continue
            dispute, created = DisputeRaffle.objects.get_or_create(case=case, component=comp, is_resolved=False)
            dispute.contenders.set(list(contenders_ids))
        else:
            DisputeRaffle.objects.filter(case=case, component=comp, is_resolved=False).delete()

    # 4. Final Cleanup
    for d in DisputeRaffle.objects.filter(case=case, is_resolved=False):
        if d.contenders.count() < 2: d.delete()

def _resolve_lottery_dispute(case, dispute, acting_user):
    contenders = list(dispute.contenders.all())
    if not contenders: 
        return None, None
    winner = random.choice(contenders)
    dispute.winner = winner
    dispute.is_resolved = True
    dispute.save(update_fields=['winner', 'is_resolved'])
    
    target = dispute.asset if dispute.asset else dispute.component
    if not target: 
        return None, None
    if isinstance(target, Asset):
        HeirAssetSelection.objects.filter(asset=target).exclude(heir=winner).delete()
        
        if target.assigned_to and target.assigned_to != winner:
            old_owner = target.assigned_to
            target.assigned_to = None
            target.save(update_fields=['assigned_to'])
            if old_owner.is_judge_confirmed:
                old_owner.allocated_share = old_owner.real_allocated_value
                old_owner.save(update_fields=['allocated_share'])
    else:
        HeirAssetSelection.objects.filter(component=target).exclude(heir=winner).delete()
        
        if target.assigned_to and target.assigned_to != winner:
            old_owner_comp = target.assigned_to
            target.assigned_to = None
            target.save(update_fields=['assigned_to'])
            if old_owner_comp.is_judge_confirmed:
                old_owner_comp.allocated_share = old_owner_comp.real_allocated_value
                old_owner_comp.save(update_fields=['allocated_share'])
                
        parent_asset = target.asset
        
        if parent_asset.assigned_to and parent_asset.assigned_to != winner:
            old_asset_owner = parent_asset.assigned_to
            parent_asset.assigned_to = None
            parent_asset.save(update_fields=['assigned_to'])
            
            for oc in parent_asset.components.exclude(id=target.id):
                oc.assigned_to = old_asset_owner
                oc.save(update_fields=['assigned_to'])
                
            if old_asset_owner.is_judge_confirmed:
                old_asset_owner.allocated_share = old_asset_owner.real_allocated_value
                old_asset_owner.save(update_fields=['allocated_share'])
                
        asset_losers = HeirAssetSelection.objects.filter(asset=parent_asset).exclude(heir=winner)
        for selection in asset_losers:
            heir = selection.heir
            selection.delete()
            for oc in parent_asset.components.exclude(id=target.id):
                HeirAssetSelection.objects.get_or_create(heir=heir, component=oc, defaults={'status': HeirAssetSelection.SelectionStatus.PENDING})

    CaseAuditLog.objects.create(case=case, action=CaseAuditLog.ActionType.RAFFLE_RESULT, description=f"القرعة على {target.description} فاز بها {winner.name}.", user=acting_user)
    
    # Update cached share if confirmed
    if winner.is_judge_confirmed:
        winner.allocated_share = winner.real_allocated_value
        winner.save(update_fields=['allocated_share'])

    return winner, target

def _build_review_context(case):
    """المنطق المركزي لبناء بيانات شاشة مراجعة القاضي"""
    reconcile_case_disputes(case)
    heirs = case.heirs.all()
    
    # 0. إصلاح وترقية النصوص في التسويات المالية الحالية تلقائياً
    for ps in PaymentSettlement.objects.filter(case=case):
        # 1. إصلاح التشويه (Mojibake)
        needs_fix = not any(c in str(ps.reason) for c in "ابتثجحخ")
        # 2. ترقية النصوص الثابتة إلى نصوص ديناميكية
        is_generic = "فرق قيمة" in str(ps.reason) and "(" not in str(ps.reason)
        
        if needs_fix or is_generic:
             heir = ps.payer
             # جمع كافة المخصصات الحالية للوريث
             items = list(heir.allocated_assets.all()) + list(heir.allocated_components.all())
             # جمع الاختيارات الحالية (intents)
             intents = HeirAssetSelection.objects.filter(heir=heir)
             intent_items = [i.asset.description if i.asset else i.component.description for i in intents]
             
             all_items = [i.description for i in items] + intent_items
             reason_suffix = f" ({'، '.join(all_items)})" if all_items else ""
             
             if ps.payer.is_judge_confirmed:
                 ps.reason = f"فرق قيمة من اختيار الأصول{reason_suffix} (بعد اعتماد القاضي)"
             else:
                 ps.reason = f"فرق قيمة اختيار الأصول{reason_suffix} (تسوية ناتجة عن التخصيص)"
             ps.save(update_fields=['reason'])

    active_disputes = DisputeRaffle.objects.filter(case=case, is_resolved=False)
    active_disputes_count = active_disputes.count()
    heir_stats = []
    all_selected = True
    
    for heir in heirs:
        intents = HeirAssetSelection.objects.filter(heir=heir).select_related('asset', 'component')
        current_selected_value = Decimal("0.00")
        intent_items = []
        heir_seen_asset_ids = set()
        
        allocated_asset_ids = set(a.id for a in heir.allocated_assets.all())
        allocated_component_ids = set(c.id for c in heir.allocated_components.all())
        
        for a in heir.allocated_assets.all(): heir_seen_asset_ids.add(a.id)

        for item in intents:
            val = get_target_effective_value(item.asset or item.component)
            target_filter = {'asset': item.asset} if item.asset else {'component': item.component}
            won_raffle = DisputeRaffle.objects.filter(case=case, winner=heir, is_resolved=True, **target_filter).exists()
            
            if item.asset:
                if item.asset.id not in allocated_asset_ids:
                    current_selected_value += val
                heir_seen_asset_ids.add(item.asset.id)
            elif item.component:
                if item.component.asset_id not in heir_seen_asset_ids and item.component.id not in allocated_component_ids:
                    current_selected_value += val

            intent_items.append({
                'name': item.asset.description if item.asset else item.component.description,
                'won_raffle': won_raffle,
                'value': val,
                'is_asset': bool(item.asset),
                'is_judge_default': False
            })

        # --- بداية التعديل: تتبع موافقة الوريث على مقترح القاضي ---
        has_accepted_proposal = AllocationProposal.objects.filter(
            case=case, heir=heir, status=AllocationProposal.Status.ACCEPTED
        ).exists()

        if not intents.exists() and not heir.is_judge_confirmed:
            for a in heir.allocated_assets.all():
                intent_items.append({
                    'name': a.description,
                    'won_raffle': False,
                    'value': get_target_effective_value(a),
                    'is_asset': True,
                    'is_judge_default': True,
                    'heir_consented': has_accepted_proposal
                })
            for c in heir.allocated_components.all():
                intent_items.append({
                    'name': c.description,
                    'won_raffle': False,
                    'value': get_target_effective_value(c),
                    'is_asset': False,
                    'is_judge_default': True,
                    'heir_consented': has_accepted_proposal
                })
        # --- نهاية التعديل ---

        formal_val = sum(a.value for a in heir.allocated_assets.all()) + \
                     sum(c.value for c in heir.allocated_components.all()) + \
                     sum(r.amount for r in PaymentSettlement.objects.filter(case=case, original_owner=heir))
        
        total_val = formal_val + current_selected_value
        diff = total_val - heir.share_value
        if not intents.exists() and formal_val == 0: all_selected = False

        heir_stats.append({
            'name': heir.name,
            'share_value': heir.share_value,
            'selected_value': total_val,
            'diff': diff,
            'obj': heir,
            'intent_items': intent_items,
            'display_status': heir.get_acceptance_status_display(),
            'status_class': 'success' if heir.is_judge_confirmed else 'info',
            'has_active_dispute': active_disputes.filter(contenders=heir).exists(),
            'allocated_items_list': (
                [{'name': a.description, 'val': a.value} for a in heir.allocated_assets.all()] +
                [{'name': c.description, 'val': c.value} for c in heir.allocated_components.all()]
            )
        })

    pending_payments = list(PaymentSettlement.objects.filter(case=case, is_paid_to_judge=False))
    for stat in heir_stats:
        if stat['diff'] > 0 and not PaymentSettlement.objects.filter(case=case, payer=stat['obj']).exists():
            # بناء قائمة بأسماء الأصول (المخصصة مسبقاً + المختارة حالياً) لتضمينها في السبب
            all_items = [i['name'] for i in stat['allocated_items_list']] + [i['name'] for i in stat['intent_items']]
            reason_suffix = f" ({'، '.join(all_items)})" if all_items else ""
            
            # FIXED: If heir is already confirmed, this is NO LONGER a draft, it must be a real settlement
            if stat['obj'].is_judge_confirmed:
                ps = PaymentSettlement.objects.create(
                    case=case, payer=stat['obj'], amount=stat['diff'],
                    reason=f"فرق قيمة الأصول{reason_suffix} (بعد حسم القرعة/التخصيص)",
                    heir_confirmed_payment=False
                )
                pending_payments.append(ps)
            else:
                pending_payments.append({
                    'payer': stat['obj'], 
                    'amount': stat['diff'],
                    'reason': f"فرق قيمة الأصول{reason_suffix} (بانتظار الاعتماد النهائي)", 
                    'is_draft': True
                })

    obligation_status = get_case_obligation_status(case)
    for item in obligation_status['items']:
        item['allocation_stage_url'] = reverse('cases:allocate_share', args=[case.id, item['obj'].id]) + f"?process_type={item['kind']}"
        item['can_open_allocation_stage'] = True
        item['has_existing_allocations'] = item['obj'].obligation_allocations.exists()

    all_balanced = not heirs.exclude(is_judge_confirmed=True).exists()
    accepted_proposal_heir_ids = list(AllocationProposal.objects.filter(case=case, status=AllocationProposal.Status.ACCEPTED).values_list('heir_id', flat=True))

    # --- بداية التعديل: حساب بيانات الرسوم البيانية ---
    from django.db.models import Sum
    total_estate_value = case.assets.aggregate(total=Sum('value'))['total'] or Decimal("0.00")
    
    # حساب القيمة المخصصة ورقياً (التي اعتمدها القاضي بالفعل)
    allocated_total = Decimal("0.00")
    for stat in heir_stats:
        allocated_total += stat['selected_value']
    
    remaining_total = total_estate_value - allocated_total
    if remaining_total < 0: remaining_total = Decimal("0.00")

    # توزيع أنواع الأصول
    asset_types = {}
    for asset in case.assets.all():
        t = asset.get_asset_type_display()
        asset_types[t] = asset_types.get(t, 0) + 1
    
    # بيانات الورثة للرسم البياني
    heir_chart_names = [s['name'] for s in heir_stats]
    heir_chart_goals = [float(s['share_value']) for s in heir_stats]
    heir_chart_currents = [float(s['selected_value']) for s in heir_stats]

    chart_data = {
        'estate_distribution': {
            'labels': ['مخصص للورثة', 'متاح للتوزيع'],
            'data': [float(allocated_total), float(remaining_total)],
        },
        'heir_progress': {
            'labels': heir_chart_names,
            'goals': heir_chart_goals,
            'currents': heir_chart_currents,
        },
        'asset_types': {
            'labels': list(asset_types.keys()),
            'data': list(asset_types.values()),
        }
    }
    # --- نهاية التعديل ---

    return {
        'case': case, 'heirs': heirs, 'heir_stats': heir_stats, 'all_selected': all_selected,
        'active_disputes_count': active_disputes_count, 'active_disputes': active_disputes,
        'pending_payments': pending_payments, 'system_warnings': get_allocation_warnings(case),
        'judge_completion_status': get_case_judge_completion_status(case), 'all_disputes_resolved': active_disputes_count == 0,
        'manual_allocation_heirs': heirs.filter(acceptance_status=Heir.AcceptanceStatus.REJECTED),
        'confirmed_heirs_count': heirs.filter(is_judge_confirmed=True).count(),
        'obligation_status': obligation_status,
        'all_balanced': all_balanced,
        'accepted_proposal_heir_ids': accepted_proposal_heir_ids,
        'chart_data': chart_data,  # تمرير بيانات الرسوم
    }

@login_required
def review_distribution(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    if request.user != case.judge: return redirect('cases:case_list')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'accept_heir':
            heir_id = request.POST.get('heir_id')
            h = get_object_or_404(Heir, id=heir_id, case=case)
            if DisputeRaffle.objects.filter(case=case, contenders=h, is_resolved=False).exists():
                messages.error(request, f"لا يمكن اعتماد الوريث {h.name} لوجود نزاعات قائمة.")
            else:
                intents = HeirAssetSelection.objects.filter(heir=h)
                # جمع أسماء الأصول المخصصة مسبقاً + الاختيارات الجديدة
                existing_items = [a.description for a in h.allocated_assets.all()] + [c.description for c in h.allocated_components.all()]
                new_items = [i.asset.description if i.asset else i.component.description for i in intents]
                all_items = existing_items + new_items
                reason_suffix = f" ({'، '.join(all_items)})" if all_items else ""
                
                # Move items and calculate real diff
                for intent in intents:
                    target = intent.asset or intent.component
                    if target and not target.assigned_to:
                        target.assigned_to = h
                        target.save()
                
                # RECALCULATE DIFF USING REAL VALUE
                real_val = h.real_allocated_value
                diff = real_val - h.share_value
                
                if diff > 0:
                    PaymentSettlement.objects.get_or_create(
                        case=case, payer=h, 
                        defaults={'amount': diff, 'reason': f"فرق قيمة من اختيار الأصول{reason_suffix} (بعد اعتماد القاضي)", 'heir_confirmed_payment': False}
                    )
                h.allocated_share = real_val
                h.acceptance_status = Heir.AcceptanceStatus.ACCEPTED
                h.is_judge_confirmed = True
                h.save()
                intents.delete()
                messages.success(request, f"تم قبول القسمة للوريث {h.name} بنجاح.")
            return redirect('cases:review_distribution', case_id=case.id)

        elif action == 'reject_heir':
            heir_id = request.POST.get('heir_id')
            h = get_object_or_404(Heir, id=heir_id, case=case)
            Asset.objects.filter(assigned_to=h, case=case).update(assigned_to=None, is_locked=False)
            AssetComponent.objects.filter(assigned_to=h, asset__case=case).update(assigned_to=None)
            PaymentSettlement.objects.filter(case=case, payer=h).delete()
            
            # --- إصلاح الخلل: تنظيف اختيارات الوريث السابقة والقرعة ---
            HeirAssetSelection.objects.filter(heir=h).delete()
            # تجريده من صفة الفائز في القرعة لتعود لمرحلة التنافس
            raffles = DisputeRaffle.objects.filter(case=case, winner=h)
            for raffle in raffles:
                raffle.winner = None
                raffle.is_resolved = False
                raffle.save(update_fields=['winner', 'is_resolved'])
            # -------------------------------------------------------------
            
            h.acceptance_status = Heir.AcceptanceStatus.REJECTED
            h.is_judge_confirmed = False
            h.allocated_share = 0
            h.save()
            messages.warning(request, f"تم رفض اختيارات {h.name} بنجاح، وتمت إضافته إلى جدول التخصيص اليدوي.")
            return redirect('cases:review_distribution', case_id=case.id)

        elif action == 'mark_paid':
            payment_id = request.POST.get('payment_id')
            payment = get_object_or_404(PaymentSettlement, id=payment_id, case=case)
            payment.is_paid_to_judge = True
            payment.save(update_fields=['is_paid_to_judge'])
            payer_name = payment.payer.name if payment.payer else ''
            messages.success(request, f"تم تأكيد استلام الدفعة من {payer_name} بنجاح.")
            return redirect('cases:review_section', case_id=case.id, section='settlements')

        elif action == 'approve':
            from .services import finalize_case_distribution
            success, message_text = finalize_case_distribution(case, request.user)
            if success:
                messages.success(request, message_text)
                return redirect('cases:final_report', case_id=case.id)
            else:
                messages.error(request, message_text)
                return redirect('cases:review_section', case_id=case.id, section='decision')

    if case.status == Case.Status.COMPLETED: return redirect('cases:final_report', case_id=case.id)
    return redirect('cases:review_section', case_id=case_id, section='overview')

@login_required
def start_lottery(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    if case.status == Case.Status.COMPLETED:
        return redirect('cases:final_report', case_id=case.id)
    
    reconcile_case_disputes(case)
    active_disputes = list(DisputeRaffle.objects.filter(case=case, is_resolved=False).prefetch_related('contenders'))
    resolved_disputes = DisputeRaffle.objects.filter(case=case, is_resolved=True).select_related('winner', 'asset', 'component')

    selected_dispute = None
    requested_dispute_id = request.GET.get('dispute')
    if requested_dispute_id:
        selected_dispute = next((dispute for dispute in active_disputes if str(dispute.id) == requested_dispute_id), None)
    if not selected_dispute and active_disputes:
        selected_dispute = active_disputes[0]

    wheel_payload = ''
    if selected_dispute:
        wheel_payload = json.dumps({
            'disputeId': selected_dispute.id,
            'assetName': selected_dispute.asset.description if selected_dispute.asset else selected_dispute.component.description,
            'assetType': 'asset' if selected_dispute.asset else 'component',
            'contenders': [{'id': c.id, 'name': c.name} for c in selected_dispute.contenders.all()],
        }, ensure_ascii=False)

    return render(request, 'cases/start_lottery.html', {
        'case': case, 'active_disputes': active_disputes, 'resolved_disputes': resolved_disputes,
        'selected_dispute': selected_dispute, 'wheel_payload': wheel_payload,
    })

@login_required
@require_POST
def run_lottery(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    dispute_id = request.POST.get('dispute_id')
    try:
        dispute = get_object_or_404(DisputeRaffle, id=dispute_id, case=case, is_resolved=False)
        winner, target = _resolve_lottery_dispute(case, dispute, request.user)
        
        if not winner or not target:
             return JsonResponse({'ok': False, 'message': 'لا يوجد متنازعين أو العنصر غير موجود.'})
             
        return JsonResponse({
            'ok': True, 
            'winnerName': winner.name, 
            'winnerId': winner.id,
            'targetName': target.description, 
            'redirectUrl': f'/cases/{case.id}/review/disputes/'
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'message': f'حدث خطأ تقني: {str(e)}'})

@login_required
def allocate_share(request, case_id, heir_id):
    case = get_object_or_404(Case, id=case_id)
    process_type = request.GET.get('process_type', 'heir')
    
    subject = None
    if process_type == 'heir':
        subject = get_object_or_404(Heir, id=heir_id, case=case)
        target_total_value = subject.share_value
        allocation_subject_name = subject.name
    elif process_type == 'debt':
        subject = get_object_or_404(Debt, id=heir_id, case=case)
        target_total_value = subject.amount
        allocation_subject_name = subject.description
    elif process_type == 'will':
        subject = get_object_or_404(Will, id=heir_id, case=case)
        target_total_value = subject.amount
        allocation_subject_name = subject.description

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'bulk_allocate':
            asset_ids = request.POST.getlist('selected_assets')
            comp_ids = request.POST.getlist('selected_components')
            settlement_ids_raw = request.POST.getlist('selected_settlements')
            
            with transaction.atomic():
                if process_type == 'heir':
                    Asset.objects.filter(assigned_to=subject).update(assigned_to=None)
                    AssetComponent.objects.filter(assigned_to=subject).update(assigned_to=None)
                    PaymentSettlement.objects.filter(original_owner=subject).update(original_owner=None)
                    
                    Asset.objects.filter(id__in=asset_ids).update(assigned_to=subject)
                    AssetComponent.objects.filter(id__in=comp_ids).update(assigned_to=subject)
                    for s_id_raw in settlement_ids_raw:
                        s_id = s_id_raw.split('_')[0]
                        PaymentSettlement.objects.filter(id=s_id).update(
                            original_owner=subject,
                            reason=F('reason') + f" (تم تخصيصه لتعويض وريث: {subject.name})"
                        )
                    # Activate Approved status
                    subject.is_judge_confirmed = True
                    subject.acceptance_status = Heir.AcceptanceStatus.ACCEPTED
                    subject.save()
                else:
                    filter_kwargs = {f"{'debt' if process_type == 'debt' else 'will_entry'}": subject}
                    case.obligation_allocations.filter(**filter_kwargs).delete()
                    for asset_id in asset_ids:
                        asset = Asset.objects.get(id=asset_id)
                        EstateObligationAllocation.objects.create(case=case, asset=asset, allocated_amount=asset.value, **filter_kwargs)
                    for comp_id in comp_ids:
                        comp = AssetComponent.objects.get(id=comp_id)
                        EstateObligationAllocation.objects.create(case=case, component=comp, allocated_amount=comp.value, **filter_kwargs)
                    for s_id_raw in settlement_ids_raw:
                        s_id = s_id_raw.split('_')[0]
                        settlement = PaymentSettlement.objects.get(id=s_id)
                        alloc_sum = EstateObligationAllocation.objects.filter(settlement=settlement).aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')
                        rem = settlement.amount - alloc_sum
                        if rem > 0:
                            EstateObligationAllocation.objects.create(case=case, settlement=settlement, allocated_amount=rem, **filter_kwargs)
            
            messages.success(request, f"تم تخصيص العناصر لـ {allocation_subject_name} بنجاح.")
            return redirect('cases:review_section', case_id=case.id, section='obligations' if process_type != 'heir' else 'overview')
            
        elif action == 'send_proposal' and process_type == 'heir':
            asset_ids = request.POST.getlist('selected_assets')
            comp_ids = request.POST.getlist('selected_components')
            settlement_ids_raw = request.POST.getlist('selected_settlements')
            
            with transaction.atomic():
                selected_assets = Asset.objects.filter(id__in=asset_ids)
                selected_components = AssetComponent.objects.filter(id__in=comp_ids)
                
                selected_items_value = sum(a.value for a in selected_assets) + sum(c.value for c in selected_components)
                for s_id_raw in settlement_ids_raw:
                    s_id = s_id_raw.split('_')[0]
                    s = PaymentSettlement.objects.get(id=s_id)
                    alloc_sum = EstateObligationAllocation.objects.filter(settlement=s).aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')
                    rem = s.amount - alloc_sum
                    if rem > 0:
                        selected_items_value += rem

                total_current_value = subject.allocated_share + selected_items_value
                diff = total_current_value - subject.share_value
                
                # Delete any existing pending proposal for this heir
                AllocationProposal.objects.filter(case=case, heir=subject, status=AllocationProposal.Status.PENDING).delete()
                
                proposal = AllocationProposal.objects.create(
                    case=case,
                    heir=subject,
                    difference_amount=diff,
                    selected_settlement_ids=','.join(settlement_ids_raw),
                    status=AllocationProposal.Status.PENDING
                )
                proposal.assets.set(selected_assets)
                proposal.components.set(selected_components)
                
                messages.success(request, f"تم إرسال المقترح إلى {subject.name} لإقرار مبلغ الفرق ({diff} ريال).")
                return redirect('cases:review_section', case_id=case.id, section='overview')

    # Recalculate Final Context
    if process_type == 'heir':
        current_allocated_value = subject.allocated_share
    else:
        filter_kwargs = {f"{'debt' if process_type == 'debt' else 'will_entry'}": subject}
        current_allocated_value = case.obligation_allocations.filter(**filter_kwargs).aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')
    reserved_asset_ids = case.obligation_allocations.filter(asset__isnull=False).values_list('asset_id', flat=True)
    reserved_comp_ids = case.obligation_allocations.filter(component__isnull=False).values_list('component_id', flat=True)
    
    # New: Exclude assets requested by heirs (HeirAssetSelection) unless they were rejected by judge
    requested_asset_ids = HeirAssetSelection.objects.filter(
        heir__case=case, 
        asset__isnull=False
    ).exclude(status=HeirAssetSelection.SelectionStatus.REJECTED).values_list('asset_id', flat=True)
    
    requested_comp_ids = HeirAssetSelection.objects.filter(
        heir__case=case, 
        component__isnull=False
    ).exclude(status=HeirAssetSelection.SelectionStatus.REJECTED).values_list('component_id', flat=True)

    available_assets = Asset.objects.filter(
        case=case, 
        components__isnull=True, 
        assigned_to__isnull=True,
        is_locked=False,
        is_sold_by_heir=False
    ).exclude(id__in=reserved_asset_ids).exclude(id__in=requested_asset_ids)
    
    available_components = AssetComponent.objects.filter(
        asset__case=case, 
        assigned_to__isnull=True,
        is_sold_by_heir=False,
        asset__assigned_to__isnull=True, # Prevent allocating parts of an assigned asset
        asset__is_locked=False            # Prevent allocating parts of a locked asset
    ).exclude(id__in=reserved_comp_ids).exclude(asset_id__in=reserved_asset_ids).exclude(id__in=requested_comp_ids).exclude(asset_id__in=requested_asset_ids) # Prevent allocating parts of a reserved or requested asset
    
    all_settlements = PaymentSettlement.objects.filter(case=case, original_owner__isnull=True)
    available_settlements = []
    for s in all_settlements:
        alloc_sum = EstateObligationAllocation.objects.filter(settlement=s).aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')
        rem = s.amount - alloc_sum
        if rem > 0.01:
            s.available_amount = rem
            s.type = 'ps'
            available_settlements.append(s)

    active_proposal = None
    proposal_asset_ids = []
    proposal_comp_ids = []
    proposal_settlement_ids = []
    
    if process_type == 'heir':
        active_proposal = AllocationProposal.objects.filter(
            case=case, heir=subject, status__in=[AllocationProposal.Status.PENDING, AllocationProposal.Status.ACCEPTED]
        ).order_by('-created_at').first()
        
        if active_proposal:
            proposal_asset_ids = [str(a.id) for a in active_proposal.assets.all()]
            proposal_comp_ids = [str(c.id) for c in active_proposal.components.all()]
            if active_proposal.selected_settlement_ids:
                proposal_settlement_ids = active_proposal.selected_settlement_ids.split(",")

    return render(request, 'cases/allocate_share.html', {
        'case': case, 
        'heir': subject if process_type == 'heir' else None,
        'allocation_subject_name': allocation_subject_name,
        'target_total_value': target_total_value,
        'current_allocated_value': current_allocated_value,
        'available_assets': available_assets, 
        'available_components': available_components,
        'available_settlements': available_settlements,
        'process_type': process_type,
        'is_debt_process': process_type == 'debt',
        'is_will_process': process_type == 'will',
        'is_heir_process': process_type == 'heir',
        'active_proposal': active_proposal,
        'proposal_asset_ids': proposal_asset_ids,
        'proposal_comp_ids': proposal_comp_ids,
        'proposal_settlement_ids': proposal_settlement_ids,
        'save_button_label': "تأكيد التخصيص والاعتماد"
    })

@login_required
def review_section(request, case_id, section):
    case = get_object_or_404(Case, id=case_id)
    if section not in REVIEW_SECTION_LABELS: section = 'overview'
    context = _build_review_context(case)
    context.update({'review_sections': REVIEW_SECTION_LABELS, 'active_review_section': section, 'section_template': f'cases/review_sections/{section}.html'})
    return render(request, 'cases/review_dashboard.html', context)

@login_required
def final_report(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    heir_data = []
    for h in case.heirs.all():
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
        })
    return render(request, 'cases/final_report.html', {'case': case, 'heir_data': heir_data})

@login_required
def toggle_heir_selection(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    case.allow_heir_selection = not case.allow_heir_selection
    case.save()
    messages.success(request, "تم تغيير حالة فتح بوابة الورثة.")
    return redirect('cases:review_distribution', case_id=case.id)

@login_required
def case_timeline(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    logs = case.audit_logs.all().order_by('-created_at')
    return render(request, 'cases/case_timeline.html', {'case': case, 'logs': logs})

@login_required
def case_call_window(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    if request.user != case.judge: return redirect('cases:case_list')
    return render(request, 'cases/call_window.html', {'case': case})
