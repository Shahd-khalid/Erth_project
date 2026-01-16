from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

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
]
