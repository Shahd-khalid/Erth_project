from django.db import models
from cases.models import Case, Heir
from django.utils.translation import gettext_lazy as _

class CalculationResult(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='calculations', verbose_name=_('القضية'))
    total_estate = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('إجمالي التركة'))
    net_estate = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('صافي التركة بعد الديون'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الحساب'))

    def __str__(self):
        return f"Calculation for {self.case} at {self.created_at}"

class HeirShare(models.Model):
    calculation = models.ForeignKey(CalculationResult, on_delete=models.CASCADE, related_name='shares', verbose_name=_('الحساب'))
    heir = models.ForeignKey(Heir, on_delete=models.CASCADE, related_name='shares', verbose_name=_('الوريث'))
    share_fraction = models.CharField(max_length=20, verbose_name=_('النصيب الشرعي (كسر)')) # e.g., "1/8"
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_('النصيب (%)'))
    share_value = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('قيمة النصيب'))

    def __str__(self):
        return f"{self.heir.name}: {self.share_fraction} ({self.share_value})"
