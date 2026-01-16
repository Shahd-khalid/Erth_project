from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import GeneralUserRegistrationForm, JudgeRegistrationForm, HeirRegistrationForm, ClerkRegistrationForm
from django.contrib.auth.decorators import login_required

def register_selection(request):
    return render(request, 'registration/register_selection.html')

def register_public(request):
    if request.method == 'POST':
        form = GeneralUserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
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
            
            # Send Email Notification to Admin
            send_mail(
                subject='تسجيل قاضي جديد',
                message=f'قام مستخدم جديد بالتسجيل كقاضي: {user.username}. يرجى مراجعة الطلب.',
                from_email=settings.DEFAULT_FROM_EMAIL or 'webmaster@localhost',
                recipient_list=['admin@example.com'], # In production, query actual admins
                fail_silently=True,
            )
            
            login(request, user)
            return redirect('dashboard')
    else:
        form = JudgeRegistrationForm()
    return render(request, 'registration/register_form.html', {'form': form, 'title': 'تسجيل قاضي'})

def register_heir(request):
    if request.method == 'POST':
        form = HeirRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = HeirRegistrationForm()
    return render(request, 'registration/register_form.html', {'form': form, 'title': 'تسجيل وريث'})

def register_clerk(request):
    if request.method == 'POST':
        form = ClerkRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = ClerkRegistrationForm()
    return render(request, 'registration/register_form.html', {'form': form, 'title': 'تسجيل كاتب مساعد'})

def home(request):
    return render(request, 'landing.html')

def portal(request):
    return render(request, 'home.html')

@login_required
def dashboard(request):
    user = request.user
    if user.role == 'ADMIN':
        return redirect('administration:dashboard')
    elif user.role == 'JUDGE':
        if user.verification_status != user.VerificationStatus.APPROVED:
            return render(request, 'dashboard/judge_pending.html', {'status': user.verification_status})
        return redirect('judges:dashboard')
    elif user.role == 'CLERK':
        return redirect('clerks:dashboard')
    elif user.role == 'HEIR':
        return redirect('heirs:dashboard')
    else:
        return render(request, 'dashboard/public_dashboard.html')
