from django.contrib import admin
from django.urls import path, include
from users import views as user_views
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

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
    path('administration/', include('administration.urls')),

    path('chat/', include('chat_bot.urls')),
    path('sw.js', TemplateView.as_view(template_name='sw.js', content_type='application/javascript'), name='sw.js'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
