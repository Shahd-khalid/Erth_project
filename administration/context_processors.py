from .models import AdminNotification
from .utils import get_registration_config

def admin_notifications(request):
    """
    Context processor to make admin notifications and settings available globally
    """
    context = {}
    if request.user.is_authenticated and request.user.role == 'ADMIN':
        notifications = AdminNotification.objects.filter(is_read=False)[:5]
        context['admin_notifications'] = notifications
    
    # Global registration setting
    config = get_registration_config()
    context['registration_enabled'] = config.get('registration_enabled', True)
    
    return context
