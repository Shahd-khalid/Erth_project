from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Avg, Exists, OuterRef, Q, Sum, Count, Subquery
from django.contrib import messages
from django.http import HttpResponse
from django.core.exceptions import ObjectDoesNotExist
import csv
from .models import AdminNotification, FiqhBook
from .forms import FiqhBookForm, AdminUserCreationForm, AdminCaseCreationForm
from cases.models import Case, Heir, Asset, PublicAssetListing, HeirAssetSelection, AssetComponent, Deceased
from users.models import Feedback

User = get_user_model()


def _admin_guard(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard:index')
    return None


def _case_deceased_name(case):
    try:
        deceased = case.deceased
    except ObjectDoesNotExist:
        deceased = None

    if deceased and deceased.name:
        return deceased.name

    linked_heir = (
        case.heirs.select_related('user')
        .exclude(user__isnull=True)
        .exclude(user__deceased_name__isnull=True)
        .exclude(user__deceased_name='')
        .first()
    )
    if linked_heir and linked_heir.user and linked_heir.user.deceased_name:
        return linked_heir.user.deceased_name

    return 'غير مدخل'


def _to_int(value):
    return int(value or 0)


def _ratio(part, total):
    if not total:
        return 0
    return round((part / total) * 100, 1)


def _build_choice_chart(queryset, field_name, choices, colors):
    raw_counts = queryset.values(field_name).annotate(total=Count('id'))
    counts_map = {row[field_name]: row['total'] for row in raw_counts}

    labels = []
    values = []
    palette = []

    for index, (key, label) in enumerate(choices):
        labels.append(str(label))
        values.append(_to_int(counts_map.get(key, 0)))
        palette.append(colors[index % len(colors)])

    return {
        'labels': labels,
        'values': values,
        'colors': palette,
        'has_data': any(values),
    }


def _case_progress(case):
    progress_map = {
        Case.Status.PENDING: 8,
        Case.Status.ASSIGNED_TO_JUDGE: 16,
        Case.Status.WITH_CLERK: 28,
        Case.Status.DATA_REVIEW: 40,
        Case.Status.READY_FOR_CALCULATION: 55,
        Case.Status.SESSION_ACTIVE: 68,
        Case.Status.CONSENT_PENDING: 76,
        Case.Status.MUTUAL_SELECTION: 82,
        Case.Status.ALTERNATIVE_SELECTION: 86,
        Case.Status.RAFFLE_PHASE: 91,
        Case.Status.PAYMENTS_PHASE: 96,
        Case.Status.COMPLETED: 100,
    }
    return progress_map.get(case.status, 0)


def _admin_metrics():
    cases_qs = Case.objects.all()
    assets_qs = Asset.objects.all()
    heirs_qs = Heir.objects.all()
    users_qs = User.objects.all()
    listings_qs = PublicAssetListing.objects.all()
    selections_qs = HeirAssetSelection.objects.all()

    total_cases = cases_qs.count()
    total_assets = assets_qs.count()
    total_heirs = heirs_qs.count()
    total_users = users_qs.count()
    total_estate_value = assets_qs.aggregate(total=Sum('value'))['total'] or 0
    total_listings = listings_qs.count()
    active_listings_count = listings_qs.filter(is_active=True).count()

    pending_judges = users_qs.filter(
        role=User.Role.JUDGE,
        verification_status=User.VerificationStatus.PENDING,
    ).count()
    pending_clerks = users_qs.filter(
        role=User.Role.CLERK,
        verification_status=User.VerificationStatus.PENDING,
    ).count()
    pending_registrations_count = pending_judges + pending_clerks

    completed_cases_count = cases_qs.filter(status=Case.Status.COMPLETED).count()
    pending_cases_count = cases_qs.exclude(status=Case.Status.COMPLETED).count()
    active_sessions_count = cases_qs.filter(
        status__in=[
            Case.Status.SESSION_ACTIVE,
            Case.Status.CONSENT_PENDING,
            Case.Status.MUTUAL_SELECTION,
            Case.Status.ALTERNATIVE_SELECTION,
            Case.Status.RAFFLE_PHASE,
            Case.Status.PAYMENTS_PHASE,
        ]
    ).count()
    assigned_cases_count = cases_qs.filter(judge__isnull=False).count()

    heir_assignments = Heir.objects.filter(user=OuterRef('pk'))
    new_heirs = users_qs.filter(role=User.Role.HEIR).annotate(
        is_assigned=Exists(heir_assignments)
    ).order_by('-date_joined')
    unassigned_heirs_count = new_heirs.filter(is_assigned=False).count()

    pending_users = users_qs.filter(
        role__in=[User.Role.JUDGE, User.Role.CLERK],
        verification_status__in=[User.VerificationStatus.PENDING, User.VerificationStatus.REJECTED],
    ).order_by('verification_status', '-date_joined')

    cases = list(cases_qs.order_by('-created_at')[:10])
    for case in cases:
        case.progress_percent = _case_progress(case)

    listings = listings_qs.order_by('-created_at')[:10]

    accepted_heirs = heirs_qs.filter(acceptance_status=Heir.AcceptanceStatus.ACCEPTED).count()
    rejected_heirs = heirs_qs.filter(acceptance_status=Heir.AcceptanceStatus.REJECTED).count()
    objection_heirs = heirs_qs.filter(
        acceptance_status=Heir.AcceptanceStatus.OBJECTION_WITH_SELECTION
    ).count()
    submitted_heirs = heirs_qs.filter(acceptance_status=Heir.AcceptanceStatus.SUBMITTED).count()
    pending_heir_decisions = heirs_qs.filter(acceptance_status=Heir.AcceptanceStatus.PENDING).count()

    heir_decision_total = accepted_heirs + rejected_heirs + objection_heirs + submitted_heirs
    approval_rate = _ratio(accepted_heirs, heir_decision_total)
    objection_rate = _ratio(rejected_heirs + objection_heirs, heir_decision_total)

    agreed_mutual_count = heirs_qs.filter(
        mutual_consent_status=Heir.MutualConsentStatus.AGREED
    ).count()
    disagreed_mutual_count = heirs_qs.filter(
        mutual_consent_status=Heir.MutualConsentStatus.DISAGREED
    ).count()

    ready_for_calculation_count = cases_qs.filter(
        status=Case.Status.READY_FOR_CALCULATION
    ).count()

    case_status_chart = _build_choice_chart(
        cases_qs,
        'status',
        Case.Status.choices,
        ['#d4af37', '#2ecc71', '#3498db', '#9b59b6', '#e67e22', '#1abc9c', '#e74c3c'],
    )
    asset_distribution_chart = _build_choice_chart(
        assets_qs,
        'asset_type',
        Asset.AssetType.choices,
        ['#d4af37', '#2ecc71', '#3498db', '#8e8e93'],
    )
    role_distribution_chart = _build_choice_chart(
        users_qs,
        'role',
        User.Role.choices,
        ['#d4af37', '#3498db', '#2ecc71', '#e67e22', '#8e8e93'],
    )
    heir_decision_chart = {
        'labels': ['مقبول', 'مرفوض', 'اعتراض', 'معلّق', 'مُرسل للمراجعة'],
        'values': [
            accepted_heirs,
            rejected_heirs,
            objection_heirs,
            pending_heir_decisions,
            submitted_heirs,
        ],
        'colors': ['#2ecc71', '#e74c3c', '#f39c12', '#95a5a6', '#3498db'],
        'has_data': any([accepted_heirs, rejected_heirs, objection_heirs, pending_heir_decisions, submitted_heirs]),
    }

    return {
        'total_cases': total_cases,
        'total_assets': total_assets,
        'total_heirs': total_heirs,
        'total_users': total_users,
        'total_estate_value': total_estate_value,
        'total_listings': total_listings,
        'active_listings_count': active_listings_count,
        'pending_registrations_count': pending_registrations_count,
        'completed_cases_count': completed_cases_count,
        'pending_cases_count': pending_cases_count,
        'active_sessions_count': active_sessions_count,
        'assigned_cases_count': assigned_cases_count,
        'unassigned_heirs_count': unassigned_heirs_count,
        'accepted_heirs_count': accepted_heirs,
        'rejected_heirs_count': rejected_heirs,
        'objection_heirs_count': objection_heirs,
        'pending_heir_decisions_count': pending_heir_decisions,
        'agreed_mutual_count': agreed_mutual_count,
        'disagreed_mutual_count': disagreed_mutual_count,
        'ready_for_calculation_count': ready_for_calculation_count,
        'approval_rate': approval_rate,
        'objection_rate': objection_rate,
        'selection_requests_count': selections_qs.count(),
        'new_heirs': new_heirs,
        'pending_users': pending_users,
        'cases': cases,
        'listings': listings,
        'case_status_chart': case_status_chart,
        'asset_distribution_chart': asset_distribution_chart,
        'role_distribution_chart': role_distribution_chart,
        'heir_decision_chart': heir_decision_chart,
    }

@login_required
def dashboard(request):
    denied = _admin_guard(request)
    if denied:
        return denied

    return render(request, 'administration/dashboard.html', _admin_metrics())


@login_required
def verification_hub(request):
    denied = _admin_guard(request)
    if denied:
        return denied

    pending_users = User.objects.filter(
        role__in=[User.Role.JUDGE, User.Role.CLERK],
        verification_status__in=[User.VerificationStatus.PENDING, User.VerificationStatus.REJECTED],
    ).order_by('verification_status', '-date_joined')

    return render(request, 'administration/verification_hub.html', {
        'pending_users': pending_users,
    })


@login_required
def case_tracking(request):
    denied = _admin_guard(request)
    if denied:
        return denied

    cases = list(Case.objects.all().order_by('-created_at'))
    for case in cases:
        case.progress_percent = _case_progress(case)
    return render(request, 'administration/case_tracking.html', {
        'cases': cases,
    })


@login_required
def create_case(request):
    if request.user.role != 'ADMIN':
        return redirect('users:dashboard')

    if request.method == 'POST':
        form = AdminCaseCreationForm(request.POST, request.FILES)
        if form.is_valid():
            judge = form.cleaned_data.get('judge')
            
            # 1. Create Case
            new_case = form.save(commit=False)
            new_case.status = Case.Status.ASSIGNED_TO_JUDGE
            new_case.save()
            
            # 2. Create Deceased linked record
            Deceased.objects.create(
                case=new_case,
                name=form.cleaned_data.get('deceased_name'),
                date_of_death=form.cleaned_data.get('date_of_death'),
                national_id=form.cleaned_data.get('national_id')
            )
            
            messages.success(request, f'تم فتح القضية رقم {new_case.display_case_number} بنجاح وإسنادها للقاضي {judge.full_name or judge.username}.')
            
            # Notify Admin Hub
            AdminNotification.objects.create(
                title='قضية جديدة مضافة',
                message=f'قام الأدمن بفتح قضية جديدة برقم {new_case.display_case_number} للمتوفى {form.cleaned_data.get("deceased_name")}',
                notification_type=AdminNotification.NotificationType.CASE_UPDATE
            )
            
            return redirect('administration:case_tracking')
        else:
            messages.error(request, 'يرجى مراجعة بيانات القضية وإصلاح الأخطاء.')
    else:
        form = AdminCaseCreationForm()

    return render(request, 'administration/create_case.html', {'form': form, 'title': 'فتح قضية إرث جديدة'})


@login_required
def edit_case(request, case_id):
    if request.user.role != 'ADMIN':
        return redirect('users:dashboard')

    case_obj = get_object_or_404(Case, id=case_id)
    try:
        deceased_obj = case_obj.deceased
    except ObjectDoesNotExist:
        deceased_obj = None

    if request.method == 'POST':
        form = AdminCaseCreationForm(request.POST, request.FILES, instance=case_obj)
        if form.is_valid():
            case_obj = form.save()
            
            # Update or Create Deceased record
            d_name = form.cleaned_data.get('deceased_name')
            d_date = form.cleaned_data.get('date_of_death')
            d_id = form.cleaned_data.get('national_id')
            
            if deceased_obj:
                deceased_obj.name = d_name
                deceased_obj.date_of_death = d_date
                deceased_obj.national_id = d_id
                deceased_obj.save()
            else:
                Deceased.objects.create(
                    case=case_obj,
                    name=d_name,
                    date_of_death=d_date,
                    national_id=d_id
                )
            
            messages.success(request, f'تم تحديث بيانات القضية رقم {case_obj.display_case_number} بنجاح.')
            return redirect('administration:case_tracking')
    else:
        initial_data = {}
        if deceased_obj:
            initial_data = {
                'deceased_name': deceased_obj.name,
                'date_of_death': deceased_obj.date_of_death,
                'national_id': deceased_obj.national_id,
            }
        form = AdminCaseCreationForm(instance=case_obj, initial=initial_data)

    return render(request, 'administration/create_case.html', {
        'form': form, 
        'title': f'تعديل القضية رقم {case_obj.display_case_number}',
        'is_edit': True
    })


@login_required
def delete_case(request, case_id):
    if request.user.role != 'ADMIN':
        return redirect('users:dashboard')
    
    if request.method == 'POST':
        case_obj = get_object_or_404(Case, id=case_id)
        case_num = case_obj.display_case_number
        case_obj.delete()
        messages.success(request, f'تم حذف القضية رقم {case_num} بنجاح من النظام.')
    
    return redirect('administration:case_tracking')


@login_required
def market_oversight(request):
    denied = _admin_guard(request)
    if denied:
        return denied

    listings = PublicAssetListing.objects.all().order_by('-created_at')
    
    active_listings_count = PublicAssetListing.objects.filter(is_active=True).count()
    sold_assets = Asset.objects.filter(is_sold_by_heir=True).order_by('-id')
    sold_components = AssetComponent.objects.filter(is_sold_by_heir=True).order_by('-id')
    
    sold_items_count = sold_assets.count() + sold_components.count()
    
    market_chart_data = {
        'labels': ['معروض للبيع', 'تم بيعه'],
        'values': [active_listings_count, sold_items_count],
        'colors': ['#3498db', '#2ecc71']
    }
    
    return render(request, 'administration/market_oversight.html', {
        'listings': listings,
        'sold_assets': sold_assets,
        'sold_components': sold_components,
        'active_listings_count': active_listings_count,
        'sold_items_count': sold_items_count,
        'market_chart_data': market_chart_data,
    })


@login_required
def heirs_management(request):
    denied = _admin_guard(request)
    if denied:
        return denied

    case_doc_subquery = Heir.objects.filter(user=OuterRef('pk')).exclude(case__inheritance_determination_doc='').values('case__inheritance_determination_doc')[:1]
    new_heirs = User.objects.filter(role=User.Role.HEIR).annotate(
        linked_case_count=Count('heir_records', distinct=True),
        case_document=Subquery(case_doc_subquery)
    ).order_by('-date_joined')

    return render(request, 'administration/heirs_management.html', {
        'new_heirs': new_heirs,
    })


@login_required
def reporting_hub(request):
    denied = _admin_guard(request)
    if denied:
        return denied

    metrics = _admin_metrics()
    return render(request, 'administration/reporting_hub.html', metrics)


@login_required
def feedback_list(request):
    denied = _admin_guard(request)
    if denied:
        return denied

    feedback_entries = Feedback.objects.select_related('user').order_by('-date_created', '-id')
    feedback_summary = feedback_entries.exclude(rating__isnull=True).aggregate(
        average_rating=Avg('rating'),
        rating_count=Count('id'),
    )
    average_rating = feedback_summary['average_rating'] or 0
    rating_count = feedback_summary['rating_count'] or 0
    average_rating_percent = round((average_rating / 5) * 100, 1) if rating_count else 0

    return render(request, 'administration/feedback_list.html', {
        'feedback_entries': feedback_entries,
        'average_rating': average_rating,
        'rating_count': rating_count,
        'average_rating_percent': average_rating_percent,
    })

@login_required
def admin_settings(request):
    denied = _admin_guard(request)
    if denied:
        return denied
    
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
        
        # Create Case
        case = Case.objects.create(
            judge=judge,
            status=Case.Status.ASSIGNED_TO_JUDGE
        )
        case_number = case.display_case_number
        
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
    judges = User.objects.filter(role=User.Role.JUDGE).order_by('full_name', 'username')
    cases = (
        Case.objects.select_related('judge')
        .prefetch_related('heirs__user')
        .filter(judge__isnull=False)
        .order_by('-created_at')
    )

    case_options = []
    for case in cases:
        case_options.append({
            'id': case.id,
            'judge_id': case.judge_id,
            'case_number': case.display_case_number,
            'deceased_name': _case_deceased_name(case),
            'judge_name': case.judge.full_name or case.judge.username,
            'status': case.get_status_display(),
        })

    selected_judge_id = request.POST.get('judge_id', '')
    selected_case_id = request.POST.get('case_id', '')

    if request.method == 'POST':
        judge_id = request.POST.get('judge_id')
        case_id = request.POST.get('case_id')
        if not judge_id:
            messages.error(request, 'يرجى اختيار القاضي أولًا.')
        elif not case_id:
            messages.error(request, 'يرجى اختيار القضية التابعة للقاضي المحدد.')
        else:
            case = get_object_or_404(Case, id=case_id, judge_id=judge_id)

            # Link Heir to Case
            Heir.objects.create(
                case=case,
                user=heir_user,
                name=heir_user.full_name or heir_user.username,
                relationship=heir_user.relationship_to_deceased or Heir.Relationship.SON,
                gender=Heir.Gender.MALE
            )
            messages.success(request, f'تم إسناد الوريث إلى القضية رقم {case.display_case_number} بنجاح.')
            return redirect('administration:dashboard')

    return render(request, 'administration/assign_existing.html', {
        'heir_user': heir_user,
        'judges': judges,
        'case_options': case_options,
        'selected_judge_id': str(selected_judge_id),
        'selected_case_id': str(selected_case_id),
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
            (case.judge.full_name or case.judge.username) if case.judge else 'غير معين',
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
    
    total_heirs = User.objects.filter(role=User.Role.HEIR).count()
    total_cases = cases.count()
    solved_cases = cases.filter(status=Case.Status.COMPLETED).count()
    approved_judges = User.objects.filter(role=User.Role.JUDGE, verification_status=User.VerificationStatus.APPROVED).count()
    
    return render(request, 'administration/report_print.html', {
        'cases': cases,
        'total_value': total_value,
        'pending_count': pending_count,
        'total_heirs': total_heirs,
        'total_cases': total_cases,
        'solved_cases': solved_cases,
        'approved_judges': approved_judges,
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
        users = users.filter(Q(username__icontains=query) | Q(full_name__icontains=query))
        
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
        
@login_required
def create_user(request):
    if request.user.role != 'ADMIN':
        return redirect('users:dashboard')

    if request.method == 'POST':
        form = AdminUserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            
            # Link to Case if it's an Heir and a case was selected
            selected_case = form.cleaned_data.get('selected_case')
            if new_user.role == User.Role.HEIR and selected_case:
                from cases.models import Heir as HeirRecord
                HeirRecord.objects.create(
                    case=selected_case,
                    user=new_user,
                    name=new_user.full_name or new_user.username,
                    relationship=form.cleaned_data.get('relationship') or HeirRecord.Relationship.SON,
                    gender=new_user.gender or HeirRecord.Gender.MALE
                )
                messages.success(request, f'تم إنشاء حساب الوريث {new_user.username} وربطه بالقضية {selected_case.display_case_number} بنجاح.')
            else:
                messages.success(request, f'تم إنشاء الحساب للمستخدم {new_user.username} بنجاح كـ {new_user.get_role_display()}.')
            
            # Send Email
            from django.core.mail import send_mail
            from django.conf import settings
            
            if new_user.email:
                subject = 'تم إنشاء حسابك في منصة المواريث'
                message = f'مرحباً {new_user.full_name or new_user.username}،\n\n' \
                          f'تم إنشاء حساب لك كـ {new_user.get_role_display()}.\n' \
                          f'اسم المستخدم: {new_user.username}\n' \
                          f'كلمة المرور: {request.POST.get("password")}\n\n' \
                          f'يرجى الدخول وتغيير كلمة المرور من إعدادات الحساب.'
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL or 'webmaster@localhost',
                    recipient_list=[new_user.email],
                    fail_silently=True,
                )
                
            return redirect('administration:user_management')
        else:
            messages.error(request, 'يرجى مراجعة الحقول وإصلاح الأخطاء.')
    else:
        form = AdminUserCreationForm()

    return render(request, 'administration/create_user.html', {'form': form})


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

@login_required
def upload_fiqh_book(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard:index')
    
    if request.method == 'POST':
        form = FiqhBookForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم رفع الكتاب الفقهي بنجاح.')
            return redirect('dashboard:library')
    else:
        form = FiqhBookForm()
        
    return render(request, 'administration/upload_book.html', {'form': form, 'is_edit': False})

@login_required
def edit_fiqh_book(request, book_id):
    if request.user.role != 'ADMIN':
        return redirect('dashboard:index')
    
    book = get_object_or_404(FiqhBook, id=book_id)
    if request.method == 'POST':
        form = FiqhBookForm(request.POST, request.FILES, instance=book)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تحديث بيانات الكتاب: {book.title} بنجاح.')
            return redirect('dashboard:library')
    else:
        form = FiqhBookForm(instance=book)
        
    return render(request, 'administration/upload_book.html', {'form': form, 'book': book, 'is_edit': True})

@login_required
def delete_fiqh_book(request, book_id):
    if request.user.role != 'ADMIN' or request.method != 'POST':
        return redirect('dashboard:index')
    
    book = get_object_or_404(FiqhBook, id=book_id)
    title = book.title
    book.delete()
    messages.error(request, f'تم حذف الكتاب: {title} نهائياً.')
    return redirect('dashboard:library')
