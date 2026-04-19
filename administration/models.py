from django.conf import settings
from django.db import models
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
        default=NotificationType.SYSTEM,
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    related_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='admin_alerts',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('تنبيه إداري')
        verbose_name_plural = _('التنبيهات الإدارية')

    def __str__(self):
        return self.title


class FiqhBook(models.Model):
    title = models.CharField(max_length=255, verbose_name=_('عنوان الكتاب'))
    author = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('المؤلف'))
    pdf_file = models.FileField(upload_to='fiqh_books/', verbose_name=_('ملف الكتاب (PDF)'))
    cover_image = models.ImageField(upload_to='book_covers/', blank=True, null=True, verbose_name=_('صورة الغلاف'))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الرفع'))

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = _('كتاب فقهي')
        verbose_name_plural = _('الكتب الفقهية')

    def __str__(self):
        return self.title
