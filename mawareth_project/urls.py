from django.contrib import admin
from django.urls import path, include
from users import views as user_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', user_views.home, name='home'),
    path('users/', include('users.urls')),
    path('calculator/', include('calculator.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('cases/', include('cases.urls')),
    path('judges/', include('judges.urls')),
    path('clerks/', include('clerks.urls')),
    path('heirs/', include('heirs.urls')),
    path('admin_custom/', include('administration.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
