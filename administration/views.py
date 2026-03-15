from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef, Sum
from django.contrib import messages
from django.http import HttpResponse
import csv
from .models import AdminNotification
from cases.models import Case, Heir, Asset, PublicAssetListing

User = get_user_model()

@login_required
def dashboard(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard:index')
        
    # 1. Statistics (Command Center)
    total_cases = Case.objects.count()
    pending_judges = User.objects.filter(role=User.Role.JUDGE, verification_status=User.VerificationStatus.PENDING).count()
    pending_clerks = User.objects.filter(role=User.Role.CLERK, verification_status=User.VerificationStatus.PENDING).count()
    total_estate_value = Asset.objects.aggregate(total=Sum('value'))['total'] or 0
    active_listings_count = PublicAssetListing.objects.filter(is_active=True).count()
    
    # 2. Heirs Waiting for Assignment
    heir_assignments = Heir.objects.filter(user=OuterRef('pk'))
    new_heirs = User.objects.filter(role=User.Role.HEIR).annotate(
        is_assigned=Exists(heir_assignments)
    ).order_by('-date_joined')
    
    # 3. Verification Hub Data
    pending_users = User.objects.filter(
        role__in=[User.Role.JUDGE, User.Role.CLERK], 
        verification_status__in=[User.VerificationStatus.PENDING, User.VerificationStatus.REJECTED]
    ).order_by('verification_status', '-date_joined')

    # 4. Case Tracking Data
    cases = Case.objects.all().order_by('-created_at')[:10]
    
    # 5. Marketplace Data
    listings = PublicAssetListing.objects.all().order_by('-created_at')[:10]
    
    # 6. Notifications (now handled by context processor)
    
    return render(request, 'administration/dashboard.html', {
        'total_cases': total_cases,
        'pending_registrations_count': pending_judges + pending_clerks,
        'total_estate_value': total_estate_value,
        'active_listings_count': active_listings_count,
        'new_heirs': new_heirs,
        'pending_users': pending_users,
        'cases': cases,
        'listings': listings,
    })

@login_required
def admin_settings(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard:index')
    
    return render(request, 'administration/settings.html')

@login_required
def create_case_for_heir(request, heir_id):
    if request.user.role != 'ADMIN':
        return redirect('dashboard:index')
        
    heir_user = get_object_or_404(User, id=heir_id)
    judges = User.objects.filter(role=User.Role.JUDGE)
    
    if request.method == 'POST':
        judge_id = request.POST.get('judge_id')
        judge = get_object_or_404(User, id=judge_id)
        
        # Auto-generate case number
        last_case = Case.objects.order_by('id').last()
        next_id = (last_case.id + 1) if last_case else 1
        case_number = f"1446/CAS/{next_id}"
        
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
        
        messages.success(request, f'تم إسناد الوريث وتوليد رقم القضية {case_number} بنجاح.')
        return redirect('administration:dashboard')
        
    return render(request, 'administration/create_case.html', {'heir_user': heir_user, 'judges': judges})

@login_required
def reassign_heir(request, heir_id):
    if request.user.role != 'ADMIN' or request.method != 'POST':
        return redirect('dashboard:index')

    heir_user = get_object_or_404(User, id=heir_id)
    heir_records = Heir.objects.filter(user=heir_user)
    
    count = 0
    for heir_record in heir_records:
        case = heir_record.case
        heir_record.delete()
        count += 1
        
        if case and case.heirs.count() == 0:
            case.delete()
            
    if count > 0:
        messages.success(request, f'تم إلغاء إسناد الوريث وحذف القضية السابقة بنجاح. يمكنك الآن إعادة إسناده.')
    else:
        messages.info(request, 'الوريث غير مسند لأي قضية حالياً.')
        
    return redirect('administration:dashboard')
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
def approve_user(request, user_id):
    if request.user.role != 'ADMIN' or request.method != 'POST':
        return redirect('dashboard:index')
    
    user = get_object_or_404(User, id=user_id)
    user.verification_status = User.VerificationStatus.APPROVED
    user.is_verified = True
    user.save()
    
    messages.success(request, f'تم تفعيل حساب {user.get_role_display()}: {user.full_name or user.username} بنجاح.')
    
    # Create Notification
    AdminNotification.objects.create(
        title='تفعيل حساب جديد',
        message=f'تم تفعيل حساب {user.get_role_display()}: {user.username}',
        notification_type=AdminNotification.NotificationType.REGISTRATION,
        related_user=user
    )

    # Notification Email
    from django.core.mail import send_mail
    from django.conf import settings
    subject = 'تم تفعيل حسابك'
    message = f'مرحباً {user.full_name or user.username}، تمت الموافقة على طلبك. يمكنك الآن استخدام المنصة.'
    
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL or 'webmaster@localhost',
        recipient_list=[user.email],
        fail_silently=True,
    )
    
    return redirect('administration:dashboard')

@login_required
def reject_user(request, user_id):
    if request.user.role != 'ADMIN' or request.method != 'POST':
        return redirect('dashboard:index')
    
    user = get_object_or_404(User, id=user_id)
    user.verification_status = User.VerificationStatus.REJECTED
    user.is_verified = False
    user.save()
    
    messages.warning(request, f'تم رفض طلب {user.get_role_display()}: {user.full_name or user.username}.')
    
    return redirect('administration:dashboard')

@login_required
def toggle_listing(request, listing_id):
    if request.user.role != 'ADMIN' or request.method != 'POST':
        return redirect('dashboard:index')
    
    listing = get_object_or_404(PublicAssetListing, id=listing_id)
    listing.is_active = not listing.is_active
    listing.save()
    
    status_msg = "تنشيط" if listing.is_active else "إخفاء"
    messages.info(request, f'تم {status_msg} العرض: {listing.component.description} بنجاح.')
    
    return redirect('administration:dashboard')

@login_required
def export_cases_csv(request):
    if request.user.role != 'ADMIN':
        return redirect('users:dashboard')
        
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="monthly_operations.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['رقم القضية', 'القاضي', 'الحالة', 'تاريخ الإنشاء'])
    
    cases = Case.objects.all().order_by('-created_at')
    for case in cases:
        writer.writerow([
            case.case_number,
            case.judge.full_name or case.judge.username,
            case.get_status_display(),
            case.created_at.strftime('%Y-%m-%d')
        ])
    
    return response

@login_required
def report_print_view(request):
    if request.user.role != 'ADMIN':
        return redirect('users:dashboard')
        
    cases = Case.objects.all().order_by('-created_at')
    total_value = Asset.objects.aggregate(total=Sum('value'))['total'] or 0
    pending_count = User.objects.filter(verification_status='PENDING').count()
    
    return render(request, 'administration/report_print.html', {
        'cases': cases,
        'total_value': total_value,
        'pending_count': pending_count,
        'date': Case.objects.first().created_at if Case.objects.exists() else None
    })

@login_required
def user_management(request):
    if request.user.role != 'ADMIN':
        return redirect('users:dashboard')
    
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', 'ALL')
    
    users = User.objects.all().exclude(id=request.user.id)
    
    if query:
        users = users.filter(models.Q(username__icontains=query) | models.Q(full_name__icontains=query))
        
    if status_filter == 'APPROVED':
        users = users.filter(verification_status=User.VerificationStatus.APPROVED)
    elif status_filter == 'PENDING':
        users = users.filter(verification_status=User.VerificationStatus.PENDING)
        
    return render(request, 'administration/user_management.html', {
        'managed_users': users,
        'query': query,
        'status_filter': status_filter
    })

@login_required
def promote_to_admin(request, user_id):
    if request.user.role != 'ADMIN' or request.method != 'POST':
        return redirect('administration:user_management')
    
    user = get_object_or_404(User, id=user_id)
    if user.role != User.Role.ADMIN:
        user.previous_role = user.role
        user.role = User.Role.ADMIN
        user.save()
        messages.success(request, f'تم ترقية {user.username} إلى مدير نظام بنجاح.')
        
        AdminNotification.objects.create(
            title='ترقية مستخدم',
            message=f'تم ترقية {user.username} إلى رتبة مدير نظام.',
            notification_type=AdminNotification.NotificationType.ROLE_CHANGE,
            related_user=user
        )
        
    return redirect('administration:user_management')

@login_required
def demote_user(request, user_id):
    if request.user.role != 'ADMIN' or request.method != 'POST':
        return redirect('administration:user_management')
    
    user = get_object_or_404(User, id=user_id)
    if user.role == User.Role.ADMIN and user.previous_role:
        original_role = user.get_previous_role_display()
        user.role = user.previous_role
        user.previous_role = None
        user.save()
        messages.info(request, f'تم إلغاء ترقية {user.username} وإعادته إلى دور: {original_role}.')
        
        AdminNotification.objects.create(
            title='إلغاء ترقية',
            message=f'تمت إعادة {user.username} إلى رتبة {original_role}.',
            notification_type=AdminNotification.NotificationType.ROLE_CHANGE,
            related_user=user
        )
        
    return redirect('administration:user_management')

@login_required
def delete_user(request, user_id):
    if request.user.role != 'ADMIN' or request.method != 'POST':
        return redirect('administration:user_management')
    
    user = get_object_or_404(User, id=user_id)
    username = user.username
    user.delete()
    messages.error(request, f'تم حذف المستخدم {username} نهائياً من النظام.')
    return redirect('administration:user_management')

@login_required
def mark_notification_read(request, notif_id):
    notification = get_object_or_404(AdminNotification, id=notif_id)
    notification.is_read = True
    notification.save()
    return HttpResponse(status=204)
