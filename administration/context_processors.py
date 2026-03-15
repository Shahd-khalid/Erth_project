from .models import AdminNotification

def admin_notifications(request):
    """
    Context processor to make admin notifications available globally
    across all admin dashboard templates.
    """
    if request.user.is_authenticated and request.user.role == 'ADMIN':
        notifications = AdminNotification.objects.filter(is_read=False)[:5]
        return {'admin_notifications': notifications}
    return {}
