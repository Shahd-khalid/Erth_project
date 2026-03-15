from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class AdminNotification(models.Model):
    class NotificationType(models.TextChoices):
        REGISTRATION = 'REGISTRATION', _('طلب تسجيل جديد')
        ROLE_CHANGE = 'ROLE_CHANGE', _('تغيير في الصلاحيات')
        SYSTEM = 'SYSTEM', _('تنبيه نظام')
        CASE_UPDATE = 'CASE_UPDATE', _('تحديث قضية')

    title = models.CharField(max_length=255, verbose_name=_('العنوان'))
    message = models.TextField(verbose_name=_('الرسالة'))
    notification_type = models.CharField(
        max_length=20, 
        choices=NotificationType.choices, 
        default=NotificationType.SYSTEM
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Optional link to a user or object
    related_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='admin_alerts'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('تنبيه المدير')
        verbose_name_plural = _('تنبيهات المدير')

    def __str__(self):
        return self.title
