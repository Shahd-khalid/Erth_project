from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from .models import Asset, Heir, HeirAssetSelection, AssetComponent, Debt, Will, PaymentSettlement, DisputeRaffle, AllocationProposal, ComponentConflictRequest, Case, CaseAuditLog


def get_target_effective_value(target):
    if not target:
        return Decimal("0.00")
    if hasattr(target, "value"):
        return Decimal(str(target.value))
    if hasattr(target, "distributable_value"):
        return Decimal(str(target.distributable_value))
    return Decimal(str(target.value))


def get_case_obligation_items(case):
    items = []
    for debt in case.debts.all():
        items.append({
            "kind": "debt",
            "obj": debt,
            "label": debt.description,
            "amount": Decimal(str(debt.amount)),
            "allocated": Decimal(str(debt.allocated_amount)),
            "remaining": Decimal(str(debt.remaining_amount)),
            "is_settled": debt.is_settled,
            "allocations": list(debt.obligation_allocations.select_related("asset", "component", "component__asset")),
        })
    for will in case.wills.all():
        items.append({
            "kind": "will",
            "obj": will,
            "label": will.description,
            "amount": Decimal(str(will.amount)),
            "allocated": Decimal(str(will.allocated_amount)),
            "remaining": Decimal(str(will.remaining_amount)),
            "is_settled": will.is_settled,
            "allocations": list(will.obligation_allocations.select_related("asset", "component", "component__asset")),
        })
    return items


def are_case_obligations_settled(case):
    return not any(item["remaining"] > 0 for item in get_case_obligation_items(case))


def get_case_obligation_status(case):
    items = get_case_obligation_items(case)
    total_required = sum((item["amount"] for item in items), Decimal("0.00"))
    total_allocated = sum((item["allocated"] for item in items), Decimal("0.00"))
    total_remaining = total_required - total_allocated
    if total_remaining < 0:
        total_remaining = Decimal("0.00")
    return {
        "items": items,
        "total_required": total_required,
        "total_allocated": total_allocated,
        "total_remaining": total_remaining,
        "is_settled": all(item["is_settled"] for item in items) if items else True,
    }


def get_obligation_target_catalog(case):
    targets = []
    for asset in case.assets.prefetch_related("components", "obligation_allocations", "obligation_allocations__debt", "obligation_allocations__will_entry"):
        if not asset.components.exists():
            targets.append({
                "kind": "asset",
                "id": asset.id,
                "key": f"asset:{asset.id}",
                "label": asset.description,
                "parent_label": "",
                "gross_value": Decimal(str(asset.value)),
                "obligation_total": Decimal(str(asset.obligation_total)),
                "net_value": Decimal(str(asset.distributable_value)),
                "obj": asset,
            })
        for component in asset.components.all():
            targets.append({
                "kind": "component",
                "id": component.id,
                "key": f"component:{component.id}",
                "label": component.description,
                "parent_label": asset.description,
                "gross_value": Decimal(str(component.value)),
                "obligation_total": Decimal(str(component.obligation_total)),
                "net_value": Decimal(str(component.distributable_value)),
                "obj": component,
            })
    return targets


def get_obligation_reserved_target_ids(case):
    return {
        "asset_ids": set(
            case.obligation_allocations.filter(asset__isnull=False).values_list("asset_id", flat=True)
        ),
        "component_ids": set(
            case.obligation_allocations.filter(component__isnull=False).values_list("component_id", flat=True)
        ),
    }


def get_heir_distribution_catalog(case):
    available_assets = []
    reserved_assets = []
    available_components = []
    reserved_components = []

    assets = case.assets.prefetch_related(
        "components",
        "obligation_allocations",
        "components__obligation_allocations",
    )

    for asset in assets:
        components = list(asset.components.all())
        if Decimal(str(asset.value)) <= Decimal("0.00"):
            reserved_assets.append(asset)
        else:
            available_assets.append(asset)

        if not components:
            continue

        for component in components:
            if Decimal(str(component.value)) <= Decimal("0.00"):
                reserved_components.append(component)
            else:
                available_components.append(component)

    available_value = sum(
        (Decimal(str(asset.value)) for asset in available_assets),
        Decimal("0.00"),
    ) + sum(
        (Decimal(str(component.value)) for component in available_components),
        Decimal("0.00"),
    )
    reserved_value = sum(
        (Decimal(str(asset.value)) for asset in reserved_assets),
        Decimal("0.00"),
    ) + sum(
        (Decimal(str(component.value)) for component in reserved_components),
        Decimal("0.00"),
    )

    return {
        "available_assets": available_assets,
        "available_components": available_components,
        "reserved_assets": reserved_assets,
        "reserved_components": reserved_components,
        "available_asset_ids": {asset.id for asset in available_assets},
        "available_component_ids": {component.id for component in available_components},
        "reserved_asset_ids": {asset.id for asset in reserved_assets},
        "reserved_component_ids": {component.id for component in reserved_components},
        "distribution_summary": {
            "available_count": len(available_assets) + len(available_components),
            "available_value": available_value,
            "reserved_count": len(reserved_assets) + len(reserved_components),
            "reserved_value": reserved_value,
        },
    }


def sync_case_heir_allocated_shares(case):
    heirs = case.heirs.prefetch_related("allocated_assets", "allocated_components")
    for heir in heirs:
        assets_total = sum(
            (get_target_effective_value(asset) for asset in heir.allocated_assets.all()),
            Decimal("0.00"),
        )
        components_total = sum(
            (get_target_effective_value(component) for component in heir.allocated_components.all()),
            Decimal("0.00"),
        )
        heir.allocated_share = assets_total + components_total
        heir.save(update_fields=["allocated_share"])


def sanitize_heir_allocation_targets(case):
    catalog = get_heir_distribution_catalog(case)

    if catalog["reserved_asset_ids"]:
        Asset.objects.filter(
            case=case,
            id__in=catalog["reserved_asset_ids"],
            assigned_to__isnull=False,
        ).update(assigned_to=None, is_locked=False)

    if catalog["reserved_component_ids"]:
        AssetComponent.objects.filter(
            asset__case=case,
            id__in=catalog["reserved_component_ids"],
            assigned_to__isnull=False,
        ).update(assigned_to=None)

    sync_case_heir_allocated_shares(case)
    return catalog


def get_case_judge_completion_status(case):
    heirs = case.heirs.all()
    active_disputes = DisputeRaffle.objects.filter(case=case, is_resolved=False)
    pending_payments = PaymentSettlement.objects.filter(case=case, is_paid_to_judge=False)
    obligations_settled = are_case_obligations_settled(case)
    
    # Standard Approval: All heirs accepted via manual judge confirmation
    all_heirs_approved = heirs.exists() and not heirs.exclude(
        acceptance_status=Heir.AcceptanceStatus.ACCEPTED
    ).exists()

    # Consensus Shortcut: All heirs agreed to the judge's preliminary distribution (proposals)
    # or are already confirmed.
    all_heirs_consented = heirs.exists() and not heirs.exclude(
        id__in=AllocationProposal.objects.filter(case=case, status=AllocationProposal.Status.ACCEPTED).values('heir_id')
    ).exclude(is_judge_confirmed=True).exclude(mutual_consent_status=Heir.MutualConsentStatus.AGREED).exists()

    return {
        "all_heirs_approved": all_heirs_approved,
        "all_heirs_consented": all_heirs_consented,
        "obligations_settled": obligations_settled,
        "has_active_disputes": active_disputes.exists(),
        "active_disputes_count": active_disputes.count(),
        "has_pending_payments": pending_payments.exists(),
        "pending_payments_count": pending_payments.count(),
        "is_completed": case.status == Case.Status.COMPLETED,
        "heirs_count": heirs.count(),
        "ready": (
            case.status != Case.Status.COMPLETED and 
            obligations_settled and 
            not active_disputes.exists() and 
            not pending_payments.exists() and 
            (all_heirs_approved or all_heirs_consented)
        ),
    }


def finalize_case_distribution(case, acting_user=None):
    status = get_case_judge_completion_status(case)
    if status["is_completed"]:
        return False, "تم إنهاء هذه القضية مسبقًا."
    
    # Check if we can proceed via either Standard path or Consensus path
    can_proceed = status["ready"]
    
    if not can_proceed:
        if not status["obligations_settled"]:
            return False, "لا يمكن إنهاء القضية قبل تصفية جميع الديون والوصايا بالكامل."
        if status["has_active_disputes"]:
            return False, "لا يمكن الاعتماد النهائي لوجود نزاعات قائمة لم يتم البت فيها."
        if status["has_pending_payments"]:
            return False, "لا يمكن اعتماد القسمة لوجود مبالغ معلقة (تسويات مالية) لم يتم سدادها بعد."
        if not status["all_heirs_approved"] and not status["all_heirs_consented"]:
            return False, "لا يمكن الاعتماد لعدم إجماع الورثة بالتراضي، أو لعدم قيام القاضي لاعتماد جميع الحصص يدوياً."
    heirs = list(case.heirs.all())
    relevant_proposals = AllocationProposal.objects.filter(case=case, status__in=["PENDING", "ACCEPTED"], difference_amount__gt=0)

    with transaction.atomic():
        for heir in heirs:
            intents = HeirAssetSelection.objects.filter(heir=heir)
            for intent in intents:
                target = intent.asset or intent.component
                if not target or target.assigned_to:
                    continue
                target.assigned_to = heir
                target.save()
                heir.allocated_share += get_target_effective_value(target)

            pledge_intent = intents.filter(requires_pledge=True, pledge_amount__gt=0).first()
            if pledge_intent:
                PaymentSettlement.objects.get_or_create(
                    case=case,
                    payer=heir,
                    amount=pledge_intent.pledge_amount,
                    reason="فرق قيمة اختيار العينات (تعهد بالدفع)",
                    defaults={"heir_confirmed_payment": False},
                )

            heir.acceptance_status = Heir.AcceptanceStatus.ACCEPTED
            heir.is_judge_confirmed = True
            heir.save()

        for proposal in relevant_proposals.filter(status="ACCEPTED"):
            heir = proposal.heir
            for asset in proposal.assets.all():
                if not asset.assigned_to:
                    asset.assigned_to = heir
                    asset.save()
                    heir.allocated_share += get_target_effective_value(asset)
            for component in proposal.components.all():
                if not component.assigned_to:
                    component.assigned_to = heir
                    component.save()
                    heir.allocated_share += get_target_effective_value(component)

            if proposal.difference_amount > 0:
                PaymentSettlement.objects.get_or_create(
                    case=case,
                    payer=heir,
                    amount=proposal.difference_amount,
                    reason="فرق قيمة متفق عليه بجلسة التوزيع (عبر مقترح القاضي)",
                    defaults={"heir_confirmed_payment": False},
                )
            heir.acceptance_status = Heir.AcceptanceStatus.ACCEPTED
            heir.is_judge_confirmed = True
            heir.save()

        HeirAssetSelection.objects.filter(heir__case=case).delete()
        AllocationProposal.objects.filter(case=case).delete()

        sync_case_heir_allocated_shares(case)
        auto_allocate(case)

        case.assets.all().update(is_locked=True)
        case.heirs.all().update(
            acceptance_status=Heir.AcceptanceStatus.ACCEPTED,
            is_judge_confirmed=True,
        )
        ComponentConflictRequest.objects.filter(case=case).update(status=ComponentConflictRequest.Status.CANCELED)

        case.allow_heir_selection = False
        case.status = Case.Status.COMPLETED
        case.save(update_fields=["allow_heir_selection", "status"])

        CaseAuditLog.objects.create(
            case=case,
            action=CaseAuditLog.ActionType.FINAL_REPORT,
            description="تم إصدار محضر القسمة النهائي واعتماد التوزيع رسميًا وإغلاق القضية.",
            user=acting_user,
        )

    return True, "تم اعتماد التوزيع بنجاح وإغلاق القضية رسميًا."

def auto_allocate(case):
    """
    Distributes remaining unassigned assets and cash pool among heirs proportionally 
    to their remaining share value.
    """
    from django.db.models import Sum
    
    unassigned_assets_val = Asset.objects.filter(case=case, assigned_to__isnull=True).aggregate(total=Sum('value'))['total'] or Decimal('0')
    unassigned_comps_val = AssetComponent.objects.filter(asset__case=case, assigned_to__isnull=True).aggregate(total=Sum('value'))['total'] or Decimal('0')
    
    # Calculate cash owed to the estate by heirs (liquidity from over-selections)
    # PaymentSettlements that have no original_owner are typically owed to the estate pool
    settlements_owed = PaymentSettlement.objects.filter(case=case, original_owner__isnull=True).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    total_pool = unassigned_assets_val + unassigned_comps_val + settlements_owed
    
    heirs = case.heirs.all()
    
    # Calculate who still needs more
    heirs_needing_more = []
    total_shares_needing_more = Decimal('0')
    
    for heir in heirs:
        rem = heir.remaining_share()
        if rem > 0:
            heirs_needing_more.append((heir, rem))
            total_shares_needing_more += rem
            
    if total_shares_needing_more == 0 or total_pool <= 0:
        # Everyone got their share, or there is nothing in the pool
        return

    # Proportional distribution of the total unassigned value
    for heir, rem in heirs_needing_more:
        proportion = rem / total_shares_needing_more
        allocated_from_pool = total_pool * proportion
        # Ensure we do not exceed the remaining share mathematically
        if allocated_from_pool > rem:
            allocated_from_pool = rem
            
        heir.allocated_share += allocated_from_pool
        heir.save()

def get_allocation_warnings(case):
    """
    Returns a list of warnings for the judge:
    - Heirs who haven't selected anything.
    - Heirs whose selection exceeds their share.
    """
    warnings = []
    heirs = case.heirs.all()
    
    for heir in heirs:
        selections = HeirAssetSelection.objects.filter(heir=heir)
        if not selections.exists():
            warnings.append({
                'type': 'no_selection',
                'heir': heir,
                'message': f"الوريث {heir.name} لم يقم باختيار أي شيء بعد."
            })
        
        selected_value = sum((s.asset.value if s.asset else s.component.value) 
                            for s in selections 
                            if not (s.component and any(i.asset == s.component.asset for i in selections)))
        if selected_value > heir.share_value:
            diff = selected_value - heir.share_value
            warnings.append({
                'type': 'over_selection',
                'heir': heir,
                'diff': diff,
                'message': f"الوريث {heir.name} اختار أصولاً بقيمة {selected_value}، وهي تتجاوز نصيبه بمقدار {diff}."
            })
            
    return warnings
