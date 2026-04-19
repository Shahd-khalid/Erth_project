from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import GeneralUserRegistrationForm, JudgeRegistrationForm, HeirRegistrationForm, ClerkRegistrationForm, FeedbackForm
from django.contrib.auth.decorators import login_required
from administration.models import AdminNotification
from cases.models import PublicAssetListing, Case, Asset
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Avg, Count
from .models import Feedback, User

def register_selection(request):
    return render(request, 'registration/register_selection.html')

def register_public(request):
    if request.method == 'POST':
        form = GeneralUserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('users:dashboard')
    else:
        form = GeneralUserRegistrationForm()
    return render(request, 'registration/register_form.html', {'form': form, 'title': 'تسجيل مستخدم عام'})

def register_judge(request):
    if request.method == 'POST':
        form = JudgeRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Create Admin Notification
            AdminNotification.objects.create(
                title='طلب انضمام قاضي',
                message=f'قام {user.username} بتقديم طلب انضمام كقاضي. يرجى مراجعة الوثائق.',
                notification_type=AdminNotification.NotificationType.REGISTRATION,
                related_user=user
            )

            # Send Email Notification to Admin
            send_mail(
                subject='تسجيل قاضي جديد',
                message=f'قام مستخدم جديد بالتسجيل كقاضي: {user.username}. يرجى مراجعة الطلب.',
                from_email=settings.DEFAULT_FROM_EMAIL or 'webmaster@localhost',
                recipient_list=['admin@example.com'], # In production, query actual admins
                fail_silently=True,
            )
            
            login(request, user)
            return redirect('users:dashboard')
    else:
        form = JudgeRegistrationForm()
    return render(request, 'registration/register_form.html', {'form': form, 'title': 'تسجيل قاضي'})

def register_heir(request):
    if request.method == 'POST':
        form = HeirRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('users:dashboard')
    else:
        form = HeirRegistrationForm()
    return render(request, 'registration/register_form.html', {'form': form, 'title': 'تسجيل وريث'})

def register_clerk(request):
    if request.method == 'POST':
        form = ClerkRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('users:dashboard')
    else:
        form = ClerkRegistrationForm()
    return render(request, 'registration/register_form.html', {'form': form, 'title': 'تسجيل كاتب مساعد'})

def home(request):
    public_listings = PublicAssetListing.objects.filter(is_active=True).select_related('component', 'component__asset', 'component__asset__case').order_by('-created_at')
    latest_listings = public_listings[:5]
    
    # Calculate stats for the hero section
    total_assets_count = Asset.objects.count()
    total_cases_count = Case.objects.count()
    
    context = {
        'public_listings': public_listings,
        'latest_listings': latest_listings,
        'total_assets_count': total_assets_count,
        'total_cases_count': total_cases_count,
    }
    return render(request, 'landing.html', context)

def portal(request):
    return render(request, 'home.html')

@login_required
def dashboard(request):
    user = request.user
    
    # Enforce verification for Judges and Clerks
    if user.role in ['JUDGE', 'CLERK'] and user.verification_status != user.VerificationStatus.APPROVED:
        return render(request, 'registration/pending_approval.html', {'status': user.verification_status})

    if user.role == 'ADMIN':
        return redirect('administration:dashboard')
    elif user.role == 'JUDGE':
        return redirect('judges:dashboard')
    elif user.role == 'CLERK':
        return redirect('clerks:dashboard')
    elif user.role == 'HEIR':
        return redirect('heirs:dashboard')
    else:
        return render(request, 'dashboard/public_dashboard.html')

@login_required
def profile_view(request):
    return _render_profile(request, initial_tab='info')


@login_required
def profile_security_view(request):
    return _render_profile(request, initial_tab='security')


@login_required
def profile_activity_view(request):
    return _render_profile(request, initial_tab='activity')


def _render_profile(request, initial_tab='info'):
    user = request.user
    stats = {}

    # Calculate statistics based on role
    if user.role == 'JUDGE':
        stats['total_cases'] = Case.objects.filter(judge=user).count()
        stats['pending_cases'] = Case.objects.filter(judge=user, status='PENDING').count()
        stats['completed_cases'] = Case.objects.filter(judge=user, status='COMPLETED').count()
    elif user.role == 'HEIR':
        stats['total_requests'] = Case.objects.filter(heirs__user=user).count()
        stats['active_requests'] = Case.objects.filter(heirs__user=user).exclude(status='COMPLETED').count()
    elif user.role == 'CLERK':
        stats['assigned_cases'] = Case.objects.filter(clerk=user).count()

    # Handle Personal Info Update (including Profile Picture & Documents)
    if request.method == 'POST' and 'update_profile' in request.POST:
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.full_name = request.POST.get('full_name', user.full_name)
        user.email = request.POST.get('email', user.email)
        user.phone_number = request.POST.get('phone_number', user.phone_number)
        
        # Role-specific fields
        if user.role == 'HEIR':
            user.gender = request.POST.get('gender', user.gender)
            user.deceased_name = request.POST.get('deceased_name', user.deceased_name)
            user.relationship_to_deceased = request.POST.get('relationship_to_deceased', user.relationship_to_deceased)
            if 'document_file' in request.FILES:
                user.document_file = request.FILES['document_file']
        
        elif user.role == 'JUDGE':
            user.judge_license = request.POST.get('judge_license', user.judge_license)
            
        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']
            
        # Admin Specific Court Identity
        if user.role == 'ADMIN':
            user.court_name = request.POST.get('court_name', user.court_name)
            user.court_address = request.POST.get('court_address', user.court_address)
            if 'official_stamp' in request.FILES:
                user.official_stamp = request.FILES['official_stamp']

        user.save()
        messages.success(request, 'تم تحديث بياناتك الشخصية بنجاح')
        return redirect('users:profile')

    # Handle Password Change
    if request.method == 'POST' and 'change_password' in request.POST:
        password_form = PasswordChangeForm(user, request.POST)
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)  # Keep user logged in
            messages.success(request, 'تم تغيير كلمة مورور بنجاح')
            return redirect('users:profile')
        else:
            for error in password_form.errors.values():
                messages.error(request, error)
    else:
        password_form = PasswordChangeForm(user)

    if initial_tab == 'activity' and not stats:
        initial_tab = 'info'

    context = {
        'stats': stats,
        'password_form': password_form,
        'initial_tab': initial_tab,
    }
    return render(request, 'users/profile.html', context)


@login_required
def feedback_view(request):
    rating_summary = Feedback.objects.exclude(rating__isnull=True).aggregate(
        average_rating=Avg('rating'),
        rating_count=Count('id'),
    )
    average_rating = rating_summary['average_rating'] or 0
    rating_count = rating_summary['rating_count'] or 0
    average_rating_percent = round((average_rating / 5) * 100, 1) if rating_count else 0
    average_rating_rounded = round(average_rating)

    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.user = request.user
            feedback.save()

            AdminNotification.objects.create(
                title='تقييم جديد من مستخدم',
                message=f'أرسل {request.user.username} تقييمًا جديدًا عبر صفحة التقييمات والملاحظات.',
                notification_type=AdminNotification.NotificationType.SYSTEM,
                related_user=request.user,
            )

            admin_emails = list(
                User.objects.filter(role=User.Role.ADMIN)
                .exclude(email='')
                .values_list('email', flat=True)
                .distinct()
            )
            if admin_emails:
                send_mail(
                    subject='تقييم جديد في منصة إرث',
                    message=(
                        f'قام المستخدم {request.user.username} بإرسال تقييم جديد.\n\n'
                        f'التقييم: {feedback.rating or "بدون تقييم"}\n'
                        f'الرسالة:\n{feedback.message}'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL or 'webmaster@localhost',
                    recipient_list=admin_emails,
                    fail_silently=True,
                )

            messages.success(request, 'تم إرسال التقييم بنجاح')
            return redirect('users:feedback')

        messages.error(request, 'يرجى مراجعة الحقول وإصلاح الأخطاء الظاهرة.')
    else:
        form = FeedbackForm()

    return render(request, 'users/feedback.html', {
        'form': form,
        'average_rating': average_rating,
        'average_rating_percent': average_rating_percent,
        'average_rating_rounded': average_rating_rounded,
        'rating_count': rating_count,
    })
