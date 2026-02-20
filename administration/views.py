from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef
from cases.models import Case, Heir

User = get_user_model()

@login_required
def dashboard(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard:index')
        
    # Get heirs who are not yet assigned to any case
    # A heir is 'assigned' if an 'Heir' model record exists for their User ID
    heir_assignments = Heir.objects.filter(user=OuterRef('pk'))
    new_heirs = User.objects.filter(role=User.Role.HEIR).annotate(
        is_assigned=Exists(heir_assignments)
    ).order_by('-date_joined')
    
    # Get count of pending judges
    pending_judges_count = User.objects.filter(role=User.Role.JUDGE, verification_status=User.VerificationStatus.PENDING).count()
    
    return render(request, 'administration/dashboard.html', {
        'new_heirs': new_heirs,
        'pending_judges_count': pending_judges_count
    })

@login_required
def create_case_for_heir(request, heir_id):
    if request.user.role != 'ADMIN':
        return redirect('dashboard:index')
        
    heir_user = get_object_or_404(User, id=heir_id)
    judges = User.objects.filter(role=User.Role.JUDGE)
    
    if request.method == 'POST':
        case_number = request.POST.get('case_number')
        judge_id = request.POST.get('judge_id')
        
        judge = get_object_or_404(User, id=judge_id)
        
        # Create Case
        case = Case.objects.create(
            case_number=case_number,
            judge=judge,
            status=Case.Status.ASSIGNED_TO_JUDGE
        )
        
        # Link Heir to Case (Create Heir record)
        Heir.objects.create(
            case=case,
            user=heir_user,
            name=heir_user.full_name or heir_user.username,
            relationship=heir_user.relationship_to_deceased or Heir.Relationship.SON,
            gender=Heir.Gender.MALE
        )
        
        return redirect('administration:dashboard')
        
    return render(request, 'administration/create_case.html', {'heir_user': heir_user, 'judges': judges})
@login_required
def assign_to_existing_case(request, heir_id):
    if request.user.role != 'ADMIN':
        return redirect('dashboard:index')

    heir_user = get_object_or_404(User, id=heir_id)
    cases = Case.objects.all().order_by('-created_at')

    if request.method == 'POST':
        case_id = request.POST.get('case_id')
        case = get_object_or_404(Case, id=case_id)

        # Link Heir to Case
        Heir.objects.create(
            case=case,
            user=heir_user,
            name=heir_user.full_name or heir_user.username,
            relationship=heir_user.relationship_to_deceased or Heir.Relationship.SON,
            gender=Heir.Gender.MALE
        )
        return redirect('administration:dashboard')

    return render(request, 'administration/assign_existing.html', {
        'heir_user': heir_user,
        'cases': cases
    })

@login_required
def judge_list(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard:index')

    pending_judges = User.objects.filter(role=User.Role.JUDGE, verification_status=User.VerificationStatus.PENDING)
    processed_judges = User.objects.filter(role=User.Role.JUDGE).exclude(verification_status=User.VerificationStatus.PENDING)

    return render(request, 'administration/judge_list.html', {
        'pending_judges': pending_judges,
        'processed_judges': processed_judges
    })

@login_required
def approve_judge(request, judge_id):
    if request.user.role != 'ADMIN' or request.method != 'POST':
        return redirect('dashboard:index')
    
    judge = get_object_or_404(User, id=judge_id)
    judge.verification_status = User.VerificationStatus.APPROVED
    judge.is_verified = True # Sync with old field
    judge.save()
    
    # Send Email Notification to Judge
    from django.core.mail import send_mail
    from django.conf import settings
    send_mail(
        subject='تمت الموافقة على حساب القاضي',
        message='مرحباً، تمت الموافقة على طلبك للتسجيل كقاضي. يمكنك الآن الدخول إلى لوحة التحكم.',
        from_email=settings.DEFAULT_FROM_EMAIL or 'webmaster@localhost',
        recipient_list=[judge.email],
        fail_silently=True,
    )
    
    return redirect('administration:judge_list')

@login_required
def reject_judge(request, judge_id):
    if request.user.role != 'ADMIN' or request.method != 'POST':
        return redirect('dashboard:index')
    
    judge = get_object_or_404(User, id=judge_id)
    judge.verification_status = User.VerificationStatus.REJECTED
    judge.is_verified = False
    judge.save()
    
    # Send Email Notification to Judge
    from django.core.mail import send_mail
    from django.conf import settings
    send_mail(
        subject='رفض طلب القاضي',
        message='نأسف لإبلاغك بأنه تم رفض طلب تسجيلك كقاضي.',
        from_email=settings.DEFAULT_FROM_EMAIL or 'webmaster@localhost',
        recipient_list=[judge.email],
        fail_silently=True,
    )
    
    return redirect('administration:judge_list')
