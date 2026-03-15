from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import GeneralUserRegistrationForm, JudgeRegistrationForm, HeirRegistrationForm, ClerkRegistrationForm
from django.contrib.auth.decorators import login_required
from administration.models import AdminNotification

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

from django.core.mail import send_mail
from django.conf import settings

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

from cases.models import PublicAssetListing

def home(request):
    public_listings = PublicAssetListing.objects.filter(is_active=True).select_related('component', 'component__asset').order_by('-created_at')
    return render(request, 'landing.html', {'public_listings': public_listings})

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

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from cases.models import Case # Import Case model to calculate stats

@login_required
def profile_view(request):
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
            messages.success(request, 'تم تغيير كلمة المرور بنجاح')
            return redirect('users:profile')
        else:
            for error in password_form.errors.values():
                messages.error(request, error)
    else:
        password_form = PasswordChangeForm(user)

    context = {
        'stats': stats,
        'password_form': password_form,
    }
    return render(request, 'users/profile.html', context)
