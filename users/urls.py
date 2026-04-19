from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'users'

urlpatterns = [
    path('register/', views.register_selection, name='register'),
    path('register/public/', views.register_public, name='register_public'),
    path('register/judge/', views.register_judge, name='register_judge'),
    path('register/clerk/', views.register_clerk, name='register_clerk'),
    path('register/heir/', views.register_heir, name='register_heir'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('portal/', views.portal, name='portal'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/security/', views.profile_security_view, name='profile_security'),
    path('profile/activity/', views.profile_activity_view, name='profile_activity'),
    path('feedback/', views.feedback_view, name='feedback'),
    
    # Password Reset URLs
    path('password_reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html',
        email_template_name='registration/password_reset_email.html',
        subject_template_name='registration/password_reset_subject.txt',
        success_url='/users/password_reset/done/'
    ), name='password_reset'),
    
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),
    
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url='/users/reset/done/'
    ), name='password_reset_confirm'),
    
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'
    ), name='password_reset_complete'),
]
