from django.shortcuts import render, redirect, get_object_or_404
from cases.models import Case, Heir, Asset, HeirAssetSelection
from django.contrib import messages
from django.contrib.auth.decorators import login_required

@login_required
def dashboard(request):
    if request.method == 'POST':
        deceased_name = request.POST.get('deceased_name')
        if deceased_name:
            user = request.user
            user.deceased_name = deceased_name
            user.save()
            messages.success(request, 'تم تحديث اسم المتوفى بنجاح.')
            return redirect('heirs:dashboard')

    # Find all heir records associated with this user
    my_heir_records = Heir.objects.filter(user=request.user)
    
    return render(request, 'heirs/dashboard.html', {
        'my_heir_records': my_heir_records
    })

def session_lobby(request, link):
    case = get_object_or_404(Case, session_link=link, status=Case.Status.SESSION_ACTIVE)
    
    return render(request, 'heirs/lobby.html', {'case': case})

def session_home(request, link, heir_id):
    case = get_object_or_404(Case, session_link=link)
    heir = get_object_or_404(Heir, id=heir_id, case=case)
    
    # Allocated Assets
    my_assets = Asset.objects.filter(case=case, assigned_to=heir)
    
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
            # Release assets? Maybe keep them designated but mark as rejected?
            # For now, let's keep them assigned until they select new ones or Judge intervenes.
            # Actually, per requirement: "Transition to stage of displaying full estate and rights to select"
            return redirect('heirs:select_assets', link=link, heir_id=heir.id)

    return render(request, 'heirs/session_home.html', {
        'case': case,
        'heir': heir,
        'my_assets': my_assets
    })

def select_assets(request, link, heir_id):
    case = get_object_or_404(Case, session_link=link)
    heir = get_object_or_404(Heir, id=heir_id, case=case)
    
    # Valid to enter if not FINALIZED (assuming ACCEPTED might be tentative, but let's allow PENDING/REJECTED)
    # User requirement: "Transition to stage..." implying everyone participates.
    
    available_assets = Asset.objects.filter(case=case, assigned_to__isnull=True) | Asset.objects.filter(case=case, assigned_to=heir)
    
    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_assets')
        confirm_balance = request.POST.get('confirm_balance')
        
        selected_assets = Asset.objects.filter(id__in=selected_ids)
        total_value = sum(a.value for a in selected_assets)
        share_value = heir.share_value
        
        diff = total_value - share_value
        # Relaxed logic: Allow any valid selection (equal, excess with confirmation, or partial)
        is_valid = True
        
        if diff > 0 and confirm_balance != 'on':
            is_valid = False
            messages.error(request, f'القيمة المختارة ({total_value}) أكبر من نصيبك. يجب الموافقة على دفع الفرق ({diff}).')

        if is_valid:
             # 1. Clear previous intents for this heir
             HeirAssetSelection.objects.filter(heir=heir).delete()
             
             # 2. Create new intents
             for asset in selected_assets:
                 wants_lottery = request.POST.get(f'lottery_{asset.id}') == 'on'
                 HeirAssetSelection.objects.create(heir=heir, asset=asset, wants_lottery=wants_lottery)
             
             # Also update direct assignment if it's NOT a conflict? 
             # Actually, for "Wishlist" stage, we should probably keep them as intents 
             # and let Judge "Finalize" them. 
             # But to keep existing functionality working for others, we can do a smart update:
             # Asset.objects.filter(case=case, assigned_to=heir).update(assigned_to=None)
             # But let's stick to intents for now as requested.

             heir.acceptance_status = Heir.AcceptanceStatus.PENDING 
             
             if diff > 0:
                 heir.allocation_description = f"تم الاختيار مع تعهد بدفع فرق: {diff}"
             elif diff < 0:
                 heir.allocation_description = f"تم اختيار أصول وقيمتها أقل من النصيب (الباقي: {abs(diff)})"
             else:
                 heir.allocation_description = "تم اختيار أصول مطابقة للنصيب"
                  
             heir.save()
             
             messages.success(request, 'تم حفظ خياراتك بنجاح. بانتظار اعتماد القاضي ومراجعة التعارضات إن وجدت.')
             return redirect('heirs:session_home', link=link, heir_id=heir.id)
    
    return render(request, 'heirs/select_assets.html', {
        'case': case,
        'heir': heir,
        'available_assets': available_assets
    })
