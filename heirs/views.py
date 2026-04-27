from django.db import models, transaction
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from cases.models import Case, Heir, Asset, HeirAssetSelection, AssetComponent, SelectionLog, DisputeRaffle, PaymentSettlement, ComponentConflictRequest, AllocationProposal, EstateObligationAllocation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

@login_required
def dashboard(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        # Handle conflict resolutions from the dashboard directly
        if action == 'cede_conflict':
            conflict_id = request.POST.get('conflict_id')
            heir_id = request.POST.get('heir_id')
            heir = get_object_or_404(Heir, id=heir_id, user=request.user)
            conflict = get_object_or_404(
                ComponentConflictRequest,
                id=conflict_id,
                owner_heir=heir,
            )
            
            target = conflict.component or conflict.parent_asset
            
            if conflict.component:
                holds_full_asset = HeirAssetSelection.objects.filter(heir=heir, asset=conflict.parent_asset).exists()
                if holds_full_asset:
                    HeirAssetSelection.objects.filter(heir=heir, asset=conflict.parent_asset).delete()
                    for comp in conflict.parent_asset.components.exclude(id=conflict.component.id):
                        HeirAssetSelection.objects.create(
                            heir=heir, component=comp,
                            status=HeirAssetSelection.SelectionStatus.ACCEPTED
                        )
                else:
                    HeirAssetSelection.objects.filter(heir=heir, component=conflict.component).delete()
            else:
                HeirAssetSelection.objects.filter(heir=heir, asset=conflict.parent_asset).delete()

            # --- TRANFER OWNERSHIP IN CORE MODELS ---
            if conflict.component:
                conflict.component.assigned_to = conflict.requesting_heir
                conflict.component.save()
            elif conflict.parent_asset:
                conflict.parent_asset.assigned_to = conflict.requesting_heir
                conflict.parent_asset.save()

            conflict.status = ComponentConflictRequest.Status.ACCEPTED
            conflict.save()

            ComponentConflictRequest.objects.filter(
                owner_heir=heir,
                component=conflict.component,
                parent_asset=conflict.parent_asset,
                status=ComponentConflictRequest.Status.PENDING
            ).exclude(id=conflict.id).update(status=ComponentConflictRequest.Status.CANCELED)
            
            messages.success(request, f'تم التنازل عن {target.description} وتحريره من اختياراتك بنجاح.')
            return redirect('heirs:dashboard')

        elif action == 'raffle_conflict':
            conflict_id = request.POST.get('conflict_id')
            heir_id = request.POST.get('heir_id')
            heir = get_object_or_404(Heir, id=heir_id, user=request.user)
            conflict = get_object_or_404(
                ComponentConflictRequest,
                id=conflict_id,
                owner_heir=heir,
            )
            
            conflict.status = ComponentConflictRequest.Status.RAFFLE_REQUIRED
            conflict.save()

            raffle, created = DisputeRaffle.objects.get_or_create(
                case=conflict.case,
                asset=conflict.parent_asset,
                component=conflict.component,
                source=DisputeRaffle.DisputeSource.MUTUAL_CONSENT,
                defaults={'is_resolved': False}
            )
            
            raffle.contenders.add(conflict.owner_heir, conflict.requesting_heir)
            raffle.save()
            
            messages.warning(request, 'تم رفض التنازل وطلب إحالة النزاع للقرعة. بانتظار نتيجة القرعة.')
            return redirect('heirs:dashboard')

        # Handle updating deceased name
        deceased_name = request.POST.get('deceased_name')
        if deceased_name:
            user = request.user
            user.deceased_name = deceased_name
            user.save()
            messages.success(request, 'تم تحديث اسم المتوفى بنجاح.')
            return redirect('heirs:dashboard')

        elif action == 'accept_proposal':
            heir_id = request.POST.get('heir_id')
            heir = get_object_or_404(Heir, id=heir_id, user=request.user)
            proposal = get_object_or_404(AllocationProposal, heir=heir, status=AllocationProposal.Status.PENDING)
            
            with transaction.atomic():
                proposal.status = AllocationProposal.Status.ACCEPTED
                proposal.save()
                
                SelectionLog.objects.create(
                    case=heir.case, heir=heir, 
                    action_text=f"تم الموافقة على التعهد بدفع فرق مالي قدره ({proposal.difference_amount}) مقابل تخصيص الأصول له."
                )
            
            messages.success(request, 'تمت الموافقة على المقترح بنجاح. بانتظار اعتماد التخصيص النهائي من القاضي.')
            return redirect('heirs:dashboard')

        elif action == 'reject_proposal':
            heir_id = request.POST.get('heir_id')
            heir = get_object_or_404(Heir, id=heir_id, user=request.user)
            proposal = get_object_or_404(AllocationProposal, heir=heir, status=AllocationProposal.Status.PENDING)
            
            proposal.status = AllocationProposal.Status.REJECTED
            proposal.save()
            
            messages.warning(request, 'تم رفض المقترح المالي.')
            return redirect('heirs:dashboard')

    # Find all heir records associated with this user
    my_heir_records = Heir.objects.filter(user=request.user)
    
    # Pre-fetch objecting heirs and settlements for each case record
    total_conflicts_count = 0
    total_proposals_count = 0
    
    for record in my_heir_records:
        case = record.case
        if case.status != Case.Status.COMPLETED:
            case.objecting_heirs = case.heirs.filter(acceptance_status=Heir.AcceptanceStatus.OBJECTION_WITH_SELECTION)
        
        # Attach allocated items and pending selections for the dashboard
        record.my_assets = record.allocated_assets.all()
        record.my_components = record.allocated_components.select_related('asset').all()
        record.my_selections = record.selections.filter(status='PENDING').select_related('asset', 'component', 'component__asset')
        
        # Settlements
        record.bills = PaymentSettlement.objects.filter(payer=record, is_paid_to_judge=False)
        record.receipts_waiting = PaymentSettlement.objects.filter(original_owner=record, is_paid_to_judge=True, is_delivered_to_owner=False)
        
        # Activity Feed
        case.recent_logs = case.selection_logs.all()[:5]

        # Conflicts Dashboard Trackers - ONLY show if already accepted/objected
        if record.acceptance_status != Heir.AcceptanceStatus.PENDING:
            record.pending_conflict_requests = ComponentConflictRequest.objects.filter(
                owner_heir=record,
                status=ComponentConflictRequest.Status.PENDING
            ).select_related('requesting_heir', 'component', 'parent_asset')
            
            record.sent_conflict_requests = ComponentConflictRequest.objects.filter(
                requesting_heir=record
            ).select_related('owner_heir', 'component', 'parent_asset')
            
            total_conflicts_count += record.pending_conflict_requests.count()
        else:
            record.pending_conflict_requests = ComponentConflictRequest.objects.none()
            record.sent_conflict_requests = ComponentConflictRequest.objects.none()

        record.active_raffles = DisputeRaffle.objects.filter(
            contenders=record,
            is_resolved=False
        ).distinct()

        record.won_raffles_list = DisputeRaffle.objects.filter(
            contenders=record,
            is_resolved=True,
            winner=record
        ).distinct()

        # Mutual Consent Proposals
        record.pending_proposals = AllocationProposal.objects.filter(
            heir=record,
            status=AllocationProposal.Status.PENDING
        ).select_related('case')
        
        total_proposals_count += record.pending_proposals.count()
    
    return render(request, 'heirs/dashboard.html', {
        'my_heir_records': my_heir_records,
        'total_conflicts_count': total_conflicts_count,
        'total_proposals_count': total_proposals_count
    })

def session_lobby(request, link):
    case = get_object_or_404(Case, session_link=link, status=Case.Status.SESSION_ACTIVE)
    
    return render(request, 'heirs/lobby.html', {'case': case})


def get_target_effective_value(target):
    return getattr(target, 'distributable_value', target.value)


def _sync_all_selection_conflicts(case):
    """
    Universal Conflict Sync:
    Detects ALL overlaps between heirs (Full vs Full, Full vs Part, Part vs Part).
    If an 'Owner' (Judge-assigned or earlier selector) is challenged by another heir,
    it creates a ComponentConflictRequest for the Owner to resolve.
    """
    all_selections = HeirAssetSelection.objects.filter(heir__case=case).select_related('heir', 'asset', 'component', 'component__asset')

    for challenge in all_selections:
        asset = challenge.asset
        comp = challenge.component
        challenger = challenge.heir

        # Find potential "Owner" (Defender) for this item
        # 1. Check if the item is explicitly assigned by the judge
        owner = None
        judge_owner = None
        if asset and asset.assigned_to:
            judge_owner = asset.assigned_to
        elif comp and comp.assigned_to:
            judge_owner = comp.assigned_to
        elif comp and comp.asset.assigned_to:
            judge_owner = comp.asset.assigned_to
            
        if judge_owner:
            if judge_owner != challenger:
                owner = judge_owner
            else:
                # If the challenger IS the judge owner, they cannot be challenging someone else
                # for their own property. Any conflict will be caught when iterating over the OTHER person's selection.
                continue
        else:
            # 2. If no judge assignment, check if someone else selected/accepted this item EARLIER
            if asset:
                earlier = HeirAssetSelection.objects.filter(
                    Q(asset=asset) | Q(component__asset=asset),
                    created_at__lt=challenge.created_at
                ).exclude(heir=challenger).order_by('created_at').first()
                if earlier:
                    owner = earlier.heir
            elif comp:
                earlier = HeirAssetSelection.objects.filter(
                    Q(component=comp) | Q(asset=comp.asset),
                    created_at__lt=challenge.created_at
                ).exclude(heir=challenger).order_by('created_at').first()
                if earlier:
                    owner = earlier.heir

        if owner and owner != challenger:
            # Create conflict request for the Owner to see
            ComponentConflictRequest.objects.get_or_create(
                case=case,
                parent_asset=asset or (comp.asset if comp else None),
                component=comp,
                requesting_heir=challenger,
                owner_heir=owner,
                defaults={
                    'status': ComponentConflictRequest.Status.PENDING,
                    'is_full_asset': comp is None
                }
            )


def _get_acceptance_conflicts(heir, case):
    """
    Finds overlaps between the assets/components assigned to 'heir'
    and what ANY other heir has selected (manually OR via judge allocation).
    Since we now use the Unified Selection model, everything is in HeirAssetSelection.
    """
    conflicts = []
    
    # 1. DEFENDER CONFLICTS: Items assigned to ME by the judge, that others have selected
    proposed_assets = Asset.objects.filter(assigned_to=heir, case=case)
    for asset in proposed_assets:
        manual_others = HeirAssetSelection.objects.filter(
            Q(asset=asset) | Q(component__asset=asset)
        ).exclude(heir=heir).select_related('heir', 'component')
        
        if manual_others.exists():
            conflicts.append({
                'item': asset,
                'item_type': 'ASSET',
                'role': 'DEFENDER',
                'claimants': list(manual_others)
            })

    proposed_components = AssetComponent.objects.filter(assigned_to=heir, asset__case=case)
    for comp in proposed_components:
        manual_others = HeirAssetSelection.objects.filter(
            Q(component=comp) | Q(asset=comp.asset)
        ).exclude(heir=heir).select_related('heir', 'asset')
        
        if manual_others.exists():
            conflicts.append({
                'item': comp,
                'item_type': 'COMPONENT',
                'role': 'DEFENDER',
                'claimants': list(manual_others)
            })
            
    # 2. CHALLENGER CONFLICTS: Items I have selected manually, that belong to someone else
    # Find all manual selections by this heir
    my_selections = HeirAssetSelection.objects.filter(heir=heir, status=HeirAssetSelection.SelectionStatus.PENDING).select_related('asset', 'component', 'component__asset')
    for sel in my_selections:
        asset = sel.asset
        comp = sel.component
        
        # Check who the true owner is
        owner = None
        judge_owner = None
        if asset and asset.assigned_to:
            judge_owner = asset.assigned_to
        elif comp and comp.assigned_to:
            judge_owner = comp.assigned_to
        elif comp and comp.asset.assigned_to:
            judge_owner = comp.asset.assigned_to
            
        if judge_owner:
            if judge_owner != heir:
                owner = judge_owner
        else:
            # No judge assignment, check if someone else picked it first
            if asset:
                earlier = HeirAssetSelection.objects.filter(
                    Q(asset=asset) | Q(component__asset=asset),
                    created_at__lt=sel.created_at
                ).exclude(heir=heir).order_by('created_at').first()
                if earlier:
                    owner = earlier.heir
            elif comp:
                earlier = HeirAssetSelection.objects.filter(
                    Q(component=comp) | Q(asset=comp.asset),
                    created_at__lt=sel.created_at
                ).exclude(heir=heir).order_by('created_at').first()
                if earlier:
                    owner = earlier.heir
                    
        if owner:
            # I am challenging someone else's property
            item = asset if asset else comp
            item_type = 'ASSET' if asset else 'COMPONENT'
            
            # Check if we already added a CHALLENGER conflict for this item
            exists = False
            for c in conflicts:
                if c['item'] == item and c['role'] == 'CHALLENGER':
                    exists = True
                    break
                    
            if not exists:
                conflicts.append({
                    'item': item,
                    'item_type': item_type,
                    'role': 'CHALLENGER',
                    'true_owner': owner,
                    'claimants': []
                })
                
    return conflicts



def session_home(request, link, heir_id):
    case = get_object_or_404(Case, session_link=link)
    heir = get_object_or_404(Heir, id=heir_id, case=case)
    
    # Unified Selection Overlap Sync
    _sync_all_selection_conflicts(case)
    
    # Allocated Items
    my_assets = heir.allocated_assets.all()
    my_components = heir.allocated_components.select_related('asset').all()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'accept':
            with transaction.atomic():
                heir.acceptance_status = Heir.AcceptanceStatus.ACCEPTED
                heir.mutual_consent_status = Heir.MutualConsentStatus.AGREED
                heir.save()
                
                # UNIFIED SYNC: Mark all pending selections for this heir as ACCEPTED
                HeirAssetSelection.objects.filter(heir=heir, status=HeirAssetSelection.SelectionStatus.PENDING).update(
                    status=HeirAssetSelection.SelectionStatus.ACCEPTED
                )

                assigned_assets = Asset.objects.filter(assigned_to=heir, case=case)
                for asset in assigned_assets:
                    HeirAssetSelection.objects.get_or_create(
                        heir=heir, asset=asset, component=None,
                        defaults={'status': HeirAssetSelection.SelectionStatus.ACCEPTED}
                    )
                assigned_components = AssetComponent.objects.filter(assigned_to=heir, asset__case=case)
                for comp in assigned_components:
                    HeirAssetSelection.objects.get_or_create(
                        heir=heir, asset=None, component=comp,
                        defaults={'status': HeirAssetSelection.SelectionStatus.ACCEPTED}
                    )

            messages.success(request, 'تم قبول القسمة بنجاح، وتم حجز نصيبك رسمياً في جدول الطلبات.')
            return redirect('heirs:session_home', link=link, heir_id=heir.id)



        elif action == 'reject_with_selection':
            # --- Clear Slate Logic for Objectors ---
            # 1. Unassign all assets and components currently allocated to the heir
            Asset.objects.filter(assigned_to=heir, case=case).update(assigned_to=None, is_locked=False)
            AssetComponent.objects.filter(assigned_to=heir, asset__case=case).update(assigned_to=None)
            
            # 2. Reset financial tracking for the heir
            heir.allocated_share = 0
            heir.is_judge_confirmed = False
            
            # 3. Delete ANY current selections/intents and debts (payer settlements)
            HeirAssetSelection.objects.filter(heir=heir).delete()
            PaymentSettlement.objects.filter(payer=heir, case=case).delete()
            
            # 4. Set status and proceed to fresh selection
            heir.acceptance_status = Heir.AcceptanceStatus.OBJECTION_WITH_SELECTION
            heir.mutual_consent_status = Heir.MutualConsentStatus.DISAGREED
            heir.save()

            # GLOBAL STATUS SYNC: Move the case to the Objection/Alternative Selection phase
            case.status = Case.Status.ALTERNATIVE_SELECTION
            case.save()
            
            # UNIFIED SYNC: Delete judge-assigned selections so heir can choose freely
            HeirAssetSelection.objects.filter(heir=heir).delete()
            
            # Resetting: delete previous automated debt/will allocations to allow judge a clean slate
            EstateObligationAllocation.objects.filter(case=case).delete()
            
            messages.success(request, 'تم تسجيل رغبتك بالرفض مع المطالبة بأصول محددة. يمكنك الآن اختيار العينات.')
            return redirect('heirs:select_assets', link=link, heir_id=heir.id)
            


        elif action == 'cede_conflict':
            conflict_id = request.POST.get('conflict_id')
            conflict = get_object_or_404(
                ComponentConflictRequest,
                id=conflict_id,
                owner_heir=heir,
            )
            
            target = conflict.component or conflict.parent_asset
            
            if conflict.component:
                holds_full_asset = HeirAssetSelection.objects.filter(heir=heir, asset=conflict.parent_asset).exists()
                if holds_full_asset:
                    HeirAssetSelection.objects.filter(heir=heir, asset=conflict.parent_asset).delete()
                    for comp in conflict.parent_asset.components.exclude(id=conflict.component.id):
                        HeirAssetSelection.objects.create(
                            heir=heir, component=comp,
                            status=HeirAssetSelection.SelectionStatus.ACCEPTED
                        )
                else:
                    HeirAssetSelection.objects.filter(heir=heir, component=conflict.component).delete()
            else:
                HeirAssetSelection.objects.filter(heir=heir, asset=conflict.parent_asset).delete()

            # --- TRANFER OWNERSHIP IN CORE MODELS ---
            # Free the current heir (who renounced) and assign to the requester (who challenged)
            if conflict.component:
                conflict.component.assigned_to = conflict.requesting_heir
                conflict.component.save()
            elif conflict.parent_asset:
                conflict.parent_asset.assigned_to = conflict.requesting_heir
                conflict.parent_asset.save()

            # Mark official
            conflict.status = ComponentConflictRequest.Status.ACCEPTED
            conflict.save()

            # Cancel any other pending requests asking THIS heir for THIS component
            ComponentConflictRequest.objects.filter(
                owner_heir=heir,
                component=conflict.component,
                parent_asset=conflict.parent_asset,
                status=ComponentConflictRequest.Status.PENDING
            ).exclude(id=conflict.id).update(status=ComponentConflictRequest.Status.CANCELED)
            
            messages.success(request, f'تم التنازل عن {target.description} وتحريره من اختياراتك بنجاح.')
            return redirect('heirs:session_home', link=link, heir_id=heir.id)

        elif action == 'raffle_conflict':
            conflict_id = request.POST.get('conflict_id')
            conflict = get_object_or_404(
                ComponentConflictRequest,
                id=conflict_id,
                owner_heir=heir,
            )
            
            conflict.status = ComponentConflictRequest.Status.RAFFLE_REQUIRED
            conflict.save()

            # --- CREATE THE DISPUTE RAFFLE RECORD ---
            # This bridges the request to the judge dashboard
            raffle, created = DisputeRaffle.objects.get_or_create(
                case=case,
                asset=conflict.parent_asset,
                component=conflict.component,
                source=DisputeRaffle.DisputeSource.MUTUAL_CONSENT,
                defaults={'is_resolved': False}
            )
            
            # Add the two contenders (Owner and Requester)
            raffle.contenders.add(conflict.owner_heir, conflict.requesting_heir)
            raffle.save()
            
            messages.warning(request, 'تم رفض التنازل وطلب إحالة النزاع للقرعة. سيتمكن القاضي من بدء القرعة الآن.')
            return redirect('heirs:session_home', link=link, heir_id=heir.id)
            
        elif action == 'accept_proposal':
            proposal = get_object_or_404(AllocationProposal, heir=heir, status=AllocationProposal.Status.PENDING)
            proposal.status = AllocationProposal.Status.ACCEPTED
            proposal.save()
            
            SelectionLog.objects.create(
                case=case, heir=heir, 
                action_text=f"تم الموافقة على التعهد بدفع فرق مالي قدره ({proposal.difference_amount}) مقابل تخصيص الأصول له."
            )
            
            messages.success(request, 'تمت الموافقة من قبلك. بانتظار اعتماد التخصيص النهائي من القاضي.')
            return redirect('heirs:session_home', link=link, heir_id=heir.id)
            
        elif action == 'reject_proposal':
            proposal = get_object_or_404(AllocationProposal, heir=heir, status=AllocationProposal.Status.PENDING)
            proposal.status = AllocationProposal.Status.REJECTED
            proposal.save()
            
            SelectionLog.objects.create(
                case=case, heir=heir, 
                action_text=f"تم رفض التعهد بدفع فرق مالي قدره ({proposal.difference_amount})."
            )
            
            messages.error(request, 'تم رفض إقرار الدفع. تم إشعار القاضي لتعديل التوزيع الخاص بك.')
            return redirect('heirs:session_home', link=link, heir_id=heir.id)

    objecting_heirs = case.heirs.filter(acceptance_status=Heir.AcceptanceStatus.OBJECTION_WITH_SELECTION)
    
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
    
    # Unified pending conflicts (mutual and individual rejection)
    # GATE: Only show in dashboard if heir has already made their primary decision (Accept/Object)
    # If PENDING, these will be handled within the Smart Acceptance Modal later.
    pending_conflicts = []
    if heir.acceptance_status != Heir.AcceptanceStatus.PENDING:
        pending_conflicts = ComponentConflictRequest.objects.filter(
            owner_heir=heir,
            status=ComponentConflictRequest.Status.PENDING,
        ).select_related('requesting_heir', 'component', 'parent_asset')
    
    pending_proposal = AllocationProposal.objects.filter(heir=heir, status=AllocationProposal.Status.PENDING).first()

    return render(request, 'heirs/session_home.html', {
        'case': case,
        'heir': heir,
        'my_assets': my_assets,
        'my_components': my_components,
        'objecting_heirs': objecting_heirs,
        'my_bills': my_bills,
        'my_receipts': my_receipts,
        'active_disputes': active_disputes,
        'resolved_disputes': resolved_disputes,
        'pending_proposal': pending_proposal,
    })

def select_assets(request, link, heir_id):
    case = get_object_or_404(Case, session_link=link)
    heir = get_object_or_404(Heir, id=heir_id, case=case)
    
    allow_selection = case.status in [Case.Status.MUTUAL_SELECTION, Case.Status.ALTERNATIVE_SELECTION]
    if heir.acceptance_status == Heir.AcceptanceStatus.OBJECTION_WITH_SELECTION:
        allow_selection = True
        
    if not allow_selection:
        messages.error(request, 'لا يمكنك اختيار الأصول في هذه المرحلة.')
        return redirect('heirs:session_home', link=link, heir_id=heir.id)
    
    from cases.models import AssetComponent
    available_assets = Asset.objects.filter(case=case)
    available_components = AssetComponent.objects.filter(asset__case=case)
    
    # Decorate assets with selection logic for the template
    for asset in available_assets:
        asset.is_selectable = True
        asset.unavailable_reason = ""
        
        if case.status == Case.Status.MUTUAL_SELECTION:
            if asset.assigned_to:
                asset.is_selectable = False
                asset.unavailable_reason = f"مخصص لـ {asset.assigned_to.name}"
            elif asset.is_locked:
                asset.is_selectable = False
                asset.unavailable_reason = "هذا الأصل مقفل حالياً"
        # In ALTERNATIVE_SELECTION, we allow selecting even if assigned (Challenging)
        
    for comp in available_components:
        comp.is_selectable = True
        comp.unavailable_reason = ""
        
        if case.status == Case.Status.MUTUAL_SELECTION:
            if comp.assigned_to:
                comp.is_selectable = False
                comp.unavailable_reason = f"مخصص لـ {comp.assigned_to.name}"
            elif comp.asset.is_locked: # If parent asset is locked, component is locked
                comp.is_selectable = False
                comp.unavailable_reason = "الأصل التابع له هذا الجزء مقفل"
    
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
        
        # --- SCENARIO 2 DETECTION: Full Asset vs Pre-existing Components ---
        confirm_conflicts = request.POST.get('confirm_full_asset_partial_conflicts')
        full_asset_partial_conflicts = []
        
        for asset in selected_assets:
            # Check if any component of this asset is already selected by others
            conflicting_selections = HeirAssetSelection.objects.filter(
                component__asset=asset,
                asset__isnull=True
            ).exclude(heir=heir).select_related('heir', 'component')

            # --- Exclude components already ceded by this heir ---
            from cases.models import ComponentConflictRequest
            already_ceded_ids = set(ComponentConflictRequest.objects.filter(
                requesting_heir=heir,
                component__asset=asset,
                status=ComponentConflictRequest.Status.ACCEPTED
            ).values_list('component_id', flat=True))

            if already_ceded_ids:
                conflicting_selections = conflicting_selections.exclude(component_id__in=already_ceded_ids)
            
            if conflicting_selections.exists():
                comp_data = {}
                for sel in conflicting_selections:
                    if sel.component.id not in comp_data:
                        comp_data[sel.component.id] = {
                            'component': sel.component,
                            'claimants': []
                        }
                    comp_data[sel.component.id]['claimants'].append(sel)
                
                full_asset_partial_conflicts.append({
                    'asset': asset,
                    'components': list(comp_data.values())
                })

        if full_asset_partial_conflicts and confirm_conflicts != '1':
            is_valid = False
            # Return to page to show the modal
            return render(request, 'heirs/select_assets.html', {
                'case': case,
                'heir': heir,
                'estate_assets': available_assets,
                'estate_components': available_components,
                'selected_asset_ids': selected_asset_ids,
                'selected_component_ids': selected_component_ids,
                'confirm_balance_checked': confirm_balance == 'on',
                'full_asset_partial_conflicts': full_asset_partial_conflicts,
                'show_full_asset_conflict_modal': True,
                'selection_summary': {
                    'total_selected': total_value,
                    'remaining': share_value - total_value
                }
            })

        if diff > 0 and confirm_balance != 'on':
            is_valid = False
            messages.error(request, f'القيمة المختارة ({total_value}) أكبر من نصيبك. يجب إعطاء تعهد بتوفية الفرق المتبقي ({diff}).')

        if is_valid:
             HeirAssetSelection.objects.filter(heir=heir).delete()
             
             for asset in selected_assets:
                 is_chal = False
                 if asset.assigned_to and asset.assigned_to != heir:
                     is_chal = True
                 
                 HeirAssetSelection.objects.create(
                     heir=heir, asset=asset, 
                     requires_pledge=(diff>0), pledge_amount=diff if diff>0 else 0,
                     status=HeirAssetSelection.SelectionStatus.ACCEPTED,
                     is_challenging_owner=is_chal
                 )

                 # Handle any Scenario 2 conflicts confirmed via the modal
                 if full_asset_partial_conflicts:
                     for conflict_entry in full_asset_partial_conflicts:
                         if conflict_entry['asset'] == asset:
                             # Identify ceded and raffled components for this asset
                             ceded_ids = []
                             raffle_ids = []
                             for comp_conflict in conflict_entry['components']:
                                 comp_id = comp_conflict['component'].id
                                 action_val = request.POST.get(f'full_asset_conflict_action_{comp_id}')
                                 if action_val == 'cede':
                                     ceded_ids.append(comp_id)
                                 elif action_val == 'raffle':
                                     raffle_ids.append(comp_id)
                             
                             if ceded_ids:
                                 # DECOMPOSITION: Heir conceded on some parts. 
                                 # Replace full asset selection with individual component selections for the rest.
                                 HeirAssetSelection.objects.filter(heir=heir, asset=asset).delete()
                                 
                                 # Log the decomposition
                                 SelectionLog.objects.create(
                                     case=case, heir=heir,
                                     action_text=f"تنازل عن أجزاء من {asset.description}. تم تفكيك الأصل وتخصيص بقية الأجزاء له."
                                 )
                                 
                                 # Re-select all components of this asset EXCEPT the ceded ones
                                 for comp in asset.components.all():
                                     if comp.id not in ceded_ids:
                                         # Select the remainder
                                         HeirAssetSelection.objects.create(
                                             heir=heir, component=comp,
                                             requires_pledge=(diff>0), pledge_amount=diff if diff>0 else 0,
                                             status=HeirAssetSelection.SelectionStatus.ACCEPTED
                                         )
                                         
                                         # If the remainder was in conflict and they chose Raffle
                                         if comp.id in raffle_ids:
                                             for comp_conflict in conflict_entry['components']:
                                                 if comp_conflict['component'].id == comp.id:
                                                     for sel in comp_conflict['claimants']:
                                                         from cases.models import ComponentConflictRequest
                                                         ComponentConflictRequest.objects.get_or_create(
                                                             case=case, requesting_heir=heir, owner_heir=sel.heir,
                                                             component=comp, parent_asset=asset,
                                                             status=ComponentConflictRequest.Status.PENDING
                                                         )
                             else:
                                 # Normal Raffle Handling (no ceding, keeping the Full Asset selection)
                                 for comp_id in raffle_ids:
                                     for comp_conflict in conflict_entry['components']:
                                         if comp_conflict['component'].id == comp_id:
                                             comp = comp_conflict['component']
                                             for sel in comp_conflict['claimants']:
                                                 from cases.models import ComponentConflictRequest
                                                 ComponentConflictRequest.objects.get_or_create(
                                                     case=case, requesting_heir=heir, owner_heir=sel.heir,
                                                     component=comp, parent_asset=asset,
                                                     status=ComponentConflictRequest.Status.PENDING
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
                 if comp.assigned_to and comp.assigned_to != heir:
                     is_chal = True
                 HeirAssetSelection.objects.create(
                     heir=heir, component=comp, 
                     requires_pledge=(diff>0), pledge_amount=diff if diff>0 else 0,
                     status=HeirAssetSelection.SelectionStatus.ACCEPTED,
                     is_challenging_owner=is_chal
                 )
                 
                 # Log selection
                 SelectionLog.objects.create(
                     case=case, heir=heir, 
                     action_text=f"قام باختيار العينة: {comp.description} (القيمة: {comp.value}) من أصل {comp.asset.description}"
                 )
                 
                 if is_chal:
                    messages.warning(request, f'تم إرسال لـ {comp.assigned_to.name} إشعار طلب نزاع وقرعة على العينة {comp.description}.')

             heir.acceptance_status = Heir.AcceptanceStatus.SELECTION_FINISHED 
             
             if diff > 0:
                 heir.allocation_description = f"تم الاختيار مع الاستعداد بدفع فرق لزيادة الاختيار: {diff}"
             elif diff < 0:
                 heir.allocation_description = f"تم اختيار أصول وعينات ألقيمة من النصيب (الباقي: {abs(diff)})"
             else:
                 heir.allocation_description = "تم اختيار أصول مطابقة للنصيب"
                  
             heir.save()
             
             # Check if all heirs have submitted their selections
             if not case.heirs.exclude(acceptance_status__in=[Heir.AcceptanceStatus.ACCEPTED, Heir.AcceptanceStatus.SELECTION_FINISHED]).exists():
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
        'estate_assets': available_assets,
        'estate_components': available_components
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
        
    my_components = AssetComponent.objects.filter(
        assigned_to__user=request.user, 
        asset__case__status=Case.Status.COMPLETED
    ).select_related('asset', 'asset__case', 'assigned_to', 'listing').order_by('-created_at')
    
    my_assets = Asset.objects.filter(
        assigned_to__user=request.user, 
        case__status=Case.Status.COMPLETED
    ).order_by('-id')
    
    return render(request, 'heirs/my_assets_sale.html', {
        'my_components': my_components,
        'my_assets': my_assets
    })

@login_required
def mark_asset_sold(request):
    if request.user.role != 'HEIR' or request.method != 'POST':
        return redirect('dashboard')
        
    item_type = request.POST.get('item_type')
    item_id = request.POST.get('item_id')
    
    if item_type == 'asset':
        asset = get_object_or_404(Asset, id=item_id, assigned_to__user=request.user)
        asset.is_sold_by_heir = True
        asset.save(update_fields=['is_sold_by_heir'])
        messages.success(request, f"تم تحديد '{asset.description}' كمباع، وتم إخفاؤه من قائمة أصولك المتاحة.")
        
    elif item_type == 'component':
        component = get_object_or_404(AssetComponent, id=item_id, assigned_to__user=request.user)
        component.is_sold_by_heir = True
        component.save(update_fields=['is_sold_by_heir'])
        if hasattr(component, 'listing') and component.listing:
            component.listing.is_active = False
            component.listing.save(update_fields=['is_active'])
        messages.success(request, f"تم تحديد '{component.description}' كمباع، وتم إنهاء العرض وإخفاؤه من قائمة أصولك المتاحة.")
        
    return redirect('heirs:my_assets_for_sale')

@login_required
def manage_asset_listing(request, item_type, item_id):
    if request.user.role != 'HEIR' or request.method != 'POST':
        return redirect('dashboard')
        
    asset = None
    component = None
    
    if item_type == 'asset':
        asset = get_object_or_404(Asset, id=item_id, assigned_to__user=request.user)
        target_item = asset
    else:
        component = get_object_or_404(AssetComponent, id=item_id, assigned_to__user=request.user)
        target_item = component
        
    seller_name = request.POST.get('seller_name')
    seller_email = request.POST.get('seller_email')
    seller_phone = request.POST.get('seller_phone')
    price_str = request.POST.get('price', '').replace(',', '.')
    description = request.POST.get('description')
    custom_image = request.FILES.get('image')
    
    from decimal import Decimal, InvalidOperation
    try:
        final_price = Decimal(price_str) if price_str else target_item.value
    except (InvalidOperation, ValueError):
        final_price = target_item.value
        
    final_description = description if description and description.strip() else target_item.description
    
    defaults = {
        'seller_name': seller_name,
        'seller_email': seller_email,
        'seller_phone': seller_phone,
        'price': final_price,
        'description': final_description,
        'is_active': True
    }
    
    if custom_image:
        defaults['image'] = custom_image
    
    listing, created = PublicAssetListing.objects.update_or_create(
        asset=asset,
        component=component,
        defaults=defaults
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

@login_required
@require_POST
def confirm_settlement_action(request, settlement_id):
    settlement = get_object_or_404(PaymentSettlement, id=settlement_id)
    heir = get_object_or_404(Heir, user=request.user, case=settlement.case)
    action = request.POST.get('settlement_action')
    
    if action == 'confirm_payment':
        if settlement.payer == heir:
            settlement.heir_confirmed_payment = True
            settlement.save()
            messages.success(request, "تم تأكيد دفع الفرق المالي بنجاح.")
        else:
            messages.error(request, "لا تملك صلاحية تأكيد هذا الدفع.")
            
    elif action == 'confirm_receipt':
        if settlement.original_owner == heir:
            if settlement.heir_confirmed_payment:
                settlement.receiver_confirmed_payment = True
                settlement.save()
                messages.success(request, "تم تأكيد استلام المبلغ بنجاح.")
            else:
                messages.error(request, "يجب أن يقوم الدافع بتأكيد الدفع أولاً.")
        else:
            messages.error(request, "لا تملك صلاحية تأكيد استلام هذا المبلغ.")
            
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
