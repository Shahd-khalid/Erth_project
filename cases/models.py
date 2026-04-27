from decimal import Decimal

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import models, transaction
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

import uuid


class Case(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("بانتظار القاضي")
        ASSIGNED_TO_JUDGE = "ASSIGNED_TO_JUDGE", _("مقبولة (عند القاضي)")
        WITH_CLERK = "WITH_CLERK", _("عند الكاتب (إدخال البيانات)")
        DATA_REVIEW = "DATA_REVIEW", _("مراجعة البيانات (عند القاضي)")
        READY_FOR_CALCULATION = "READY_FOR_CALCULATION", _("جاهزة للحساب")
        SESSION_ACTIVE = "SESSION_ACTIVE", _("جلسة توزيع التركة جارية")
        CONSENT_PENDING = "CONSENT_PENDING", _("بانتظار موافقة الورثة (طلب تراضٍ)")
        MUTUAL_SELECTION = "MUTUAL_SELECTION", _("مرحلة التراضي (اختيار الأصول)")
        ALTERNATIVE_SELECTION = "ALTERNATIVE_SELECTION", _("مرحلة الاعتراض (اختيار بديل)")
        RAFFLE_PHASE = "RAFFLE_PHASE", _("مرحلة القرعة للنزاعات")
        PAYMENTS_PHASE = "PAYMENTS_PHASE", _("مرحلة السداد والتخارج (لوحة القاضي)")
        COMPLETED = "COMPLETED", _("مكتملة")

    class JudgeAcceptanceStatus(models.TextChoices):
        PENDING = "PENDING", _("بانتظار القبول")
        ACCEPTED = "ACCEPTED", _("مقبولة")
        REJECTED = "REJECTED", _("مرفوضة")

    case_number = models.CharField(max_length=50, unique=False, verbose_name=_("رقم القضية"))
    sequence_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("الرقم التسلسلي للقضية"),
    )
    judge = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="judged_cases",
        limit_choices_to={"role": "JUDGE"},
        verbose_name=_("القاضي"),
    )
    clerk = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clerked_cases",
        limit_choices_to={"role": "CLERK"},
        verbose_name=_("الكاتب المساعد"),
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING, verbose_name=_("الحالة"))
    judge_acceptance_status = models.CharField(
        max_length=20,
        choices=JudgeAcceptanceStatus.choices,
        default=JudgeAcceptanceStatus.PENDING,
        verbose_name=_("حالة قبول القاضي"),
    )
    session_link = models.UUIDField(default=uuid.uuid4, editable=False, verbose_name=_("رابط الجلسة"))
    is_ready_for_calculation = models.BooleanField(default=False, verbose_name=_("جاهزة للحساب"))
    judge_consents_to_mutual = models.BooleanField(default=False, verbose_name=_("موافقة القاضي على القسمة بالتراضي"))
    allow_heir_selection = models.BooleanField(default=True, verbose_name=_("السماح للورثة بالدخول لمرحلة الاختيار"))
    rejection_reason = models.TextField(blank=True, null=True, verbose_name=_("سبب الرفض"))
    inheritance_determination_doc = models.FileField(
        upload_to="inheritance_docs/", 
        blank=True, 
        null=True, 
        verbose_name=_("صك حصر الورثة")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))

    class Meta:
        unique_together = ("case_number", "judge")
        constraints = [
            models.UniqueConstraint(
                fields=["judge", "sequence_number"],
                name="unique_case_sequence_per_judge",
            ),
        ]
        verbose_name = _("القضية")
        verbose_name_plural = _("القضايا")

    def __str__(self):
        return str(self.case_number)

    @property
    def display_case_number(self):
        if self.case_number:
            return str(self.case_number)
        if self.sequence_number:
            return str(self.sequence_number)
        return "-"

    @property
    def can_open_mutual_balance(self):
        """
        Determines if the judge can open the mutual balancing (comprehensive control) interface.
        Logic: 
        Allow access if the session is active/started, UNLESS everyone has already agreed.
        """
        # 1. If everyone has already agreed, the balancing phase is effectively over (or wait for final approve)
        all_agreed = not self.heirs.exclude(mutual_consent_status="AGREED").exists()
        if all_agreed and self.status in [self.Status.SESSION_ACTIVE, self.Status.CONSENT_PENDING]:
            return False

        # 2. Allow if the case is in any distribution management phase
        allowed_statuses = [
            self.Status.SESSION_ACTIVE,
            self.Status.CONSENT_PENDING,
            self.Status.MUTUAL_SELECTION,
            self.Status.ALTERNATIVE_SELECTION,
            self.Status.RAFFLE_PHASE,
            self.Status.PAYMENTS_PHASE
        ]
        return self.status in allowed_statuses

    def _next_sequence_for_judge(self):
        user_model = get_user_model()
        user_model.objects.select_for_update().get(pk=self.judge_id)
        max_sequence = (
            Case.objects.filter(judge_id=self.judge_id)
            .exclude(pk=self.pk)
            .aggregate(max_sequence=Max("sequence_number"))
            .get("max_sequence")
            or 0
        )
        return max_sequence + 1

    def save(self, *args, **kwargs):
        previous_judge_id = None
        if self.pk:
            previous_judge_id = Case.objects.filter(pk=self.pk).values_list("judge_id", flat=True).first()

        should_assign_sequence = bool(self.judge_id) and (
            not self.sequence_number
            or not self.case_number
            or previous_judge_id != self.judge_id
        )

        if should_assign_sequence:
            with transaction.atomic():
                self.sequence_number = self._next_sequence_for_judge()
                self.case_number = str(self.sequence_number)
                return super().save(*args, **kwargs)

        if self.sequence_number and self.case_number != str(self.sequence_number):
            self.case_number = str(self.sequence_number)

        return super().save(*args, **kwargs)


class Deceased(models.Model):
    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name="deceased", verbose_name=_("القضية"))
    name = models.CharField(max_length=255, verbose_name=_("اسم المتوفى"))
    date_of_death = models.DateField(verbose_name=_("تاريخ الوفاة"))
    national_id = models.CharField(max_length=20, verbose_name=_("رقم الهوية"))

    def __str__(self):
        return self.name


class Asset(models.Model):
    class AssetType(models.TextChoices):
        REAL_ESTATE = "عقار", _("عقار")
        CASH = "نقد", _("نقد")
        STOCK = "أسهم", _("أسهم")
        OTHER = "أخرى", _("أخرى")

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="assets", verbose_name=_("القضية"))
    description = models.CharField(max_length=255, verbose_name=_("الوصف"))
    value = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("القيمة"))
    image = models.ImageField(upload_to="assets/", blank=True, null=True, verbose_name=_("صورة الأصل"))
    asset_type = models.CharField(max_length=20, choices=AssetType.choices, default=AssetType.OTHER, verbose_name=_("نوع الأصل"))
    assigned_to = models.ForeignKey("Heir", on_delete=models.SET_NULL, null=True, blank=True, related_name="allocated_assets", verbose_name=_("مخصص لـ"))
    is_locked = models.BooleanField(default=False, verbose_name=_("مقفل (تم الاختيار)"))
    is_sold_by_heir = models.BooleanField(default=False, verbose_name=_("مباع من قبل الوريث"))

    @property
    def obligation_allocations_qs(self):
        return self.obligation_allocations.select_related("debt", "will_entry")

    @property
    def obligation_total(self):
        return self.obligation_allocations_qs.aggregate(total=models.Sum("allocated_amount")).get("total") or Decimal("0.00")

    @property
    def distributable_value(self):
        net_value = Decimal(str(self.value)) - Decimal(str(self.obligation_total))
        return net_value if net_value > 0 else Decimal("0.00")

    @property
    def has_obligation_burden(self):
        return self.obligation_total > 0

    @property
    def obligation_labels(self):
        return [allocation.obligation_label for allocation in self.obligation_allocations_qs]

    def __str__(self):
        return f"{self.description} - {self.value}"


class Debt(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="debts", verbose_name=_("القضية"))
    description = models.CharField(max_length=255, verbose_name=_("وصف الدين"))
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("المبلغ"))

    @property
    def allocated_amount(self):
        return self.obligation_allocations.aggregate(total=models.Sum("allocated_amount")).get("total") or Decimal("0.00")

    @property
    def remaining_amount(self):
        remaining = Decimal(str(self.amount)) - Decimal(str(self.allocated_amount))
        return remaining if remaining > 0 else Decimal("0.00")

    @property
    def is_settled(self):
        return self.remaining_amount == Decimal("0.00")

    def __str__(self):
        return f"{self.description} - {self.amount}"


class Will(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="wills", verbose_name=_("القضية"))
    description = models.CharField(max_length=255, verbose_name=_("وصف الوصية"))
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("المبلغ"))

    @property
    def allocated_amount(self):
        return self.obligation_allocations.aggregate(total=models.Sum("allocated_amount")).get("total") or Decimal("0.00")

    @property
    def remaining_amount(self):
        remaining = Decimal(str(self.amount)) - Decimal(str(self.allocated_amount))
        return remaining if remaining > 0 else Decimal("0.00")

    @property
    def is_settled(self):
        return self.remaining_amount == Decimal("0.00")

    def __str__(self):
        return f"{self.description} - {self.amount}"


class Heir(models.Model):
    class Relationship(models.TextChoices):
        HUSBAND = "زوج", _("زوج")
        WIFE = "زوجة", _("زوجة")
        SON = "ابن", _("ابن")
        DAUGHTER = "بنت", _("بنت")
        FATHER = "أب", _("أب")
        MOTHER = "أم", _("أم")
        BROTHER = "أخ شقيق", _("أخ شقيق")
        SISTER = "أخت شقيقة", _("أخت شقيقة")
        SON_OF_SON = "ابن ابن", _("ابن ابن")
        DAUGHTER_OF_SON = "بنت ابن", _("بنت ابن")
        GRANDFATHER_FATHER = "جد (أبو الأب)", _("جد (أبو الأب)")
        GRANDMOTHER_FATHER = "جدة (أم الأب)", _("جدة (أم الأب)")
        GRANDMOTHER_MOTHER = "جدة (أم الأم)", _("جدة (أم الأم)")
        BROTHER_FATHER = "أخ لأب", _("أخ لأب")
        SISTER_FATHER = "أخت لأب", _("أخت لأب")
        BROTHER_MOTHER = "أخ لأم", _("أخ لأم")
        SISTER_MOTHER = "أخت لأم", _("أخت لأم")
        SON_OF_BROTHER = "ابن أخ شقيق", _("ابن أخ شقيق")
        SON_OF_BROTHER_FATHER = "ابن أخ لأب", _("ابن أخ لأب")
        UNCLE = "عم شقيق", _("عم شقيق")
        UNCLE_FATHER = "عم لأب", _("عم لأب")
        SON_OF_UNCLE = "ابن عم شقيق", _("ابن عم شقيق")
        SON_OF_UNCLE_FATHER = "ابن عم لأب", _("ابن عم لأب")

    class Gender(models.TextChoices):
        MALE = "ذكر", _("ذكر")
        FEMALE = "أنثى", _("أنثى")

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="heirs", verbose_name=_("القضية"))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="heir_records", verbose_name=_("حساب المستخدم"))
    name = models.CharField(max_length=255, verbose_name=_("الاسم"))
    relationship = models.CharField(max_length=50, choices=Relationship.choices, verbose_name=_("صلة القرابة"))
    gender = models.CharField(max_length=10, choices=Gender.choices, verbose_name=_("الجنس"))
    is_blocked = models.BooleanField(default=False, verbose_name=_("محجوب"))
    blocking_reason = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("سبب الحجب"))
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("نسبة الإرث %"))
    share_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name=_("قيمة النصيب"))
    allocated_share = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name=_("القيمة المخصصة"))
    is_judge_confirmed = models.BooleanField(default=False, verbose_name=_("تم الاعتماد النهائي من القاضي"))

    class AcceptanceStatus(models.TextChoices):
        PENDING = "PENDING", _("قيد الانتظار")
        SUBMITTED = "SUBMITTED", _("بانتظار مراجعة القاضي")
        ACCEPTED = "ACCEPTED", _("مقبول")
        REJECTED = "REJECTED", _("مرفوض")
        OBJECTION_WITH_SELECTION = "OBJECTION_WITH_SELECTION", _("رفض مع اختيار تركتي")
        SELECTION_FINISHED = "SELECTION_FINISHED", _("تم إكمال الاختيار اليدوي")

    class MutualConsentStatus(models.TextChoices):
        NOT_VOTED = "NOT_VOTED", _("لم يصوت")
        AGREED = "AGREED", _("موافق على القسمة بالتراضي")
        DISAGREED = "DISAGREED", _("غير موافق على القسمة بالتراضي")

    acceptance_status = models.CharField(max_length=50, choices=AcceptanceStatus.choices, default=AcceptanceStatus.PENDING, verbose_name=_("حالة القبول"))
    mutual_consent_status = models.CharField(max_length=20, choices=MutualConsentStatus.choices, default=MutualConsentStatus.NOT_VOTED, verbose_name=_("حالة التصويت للتراضي"))
    allocation_description = models.TextField(blank=True, verbose_name=_("وصف القسمة (رسالة القاضي)"))

    @property
    def real_allocated_value(self):
        assets_val = self.allocated_assets.aggregate(total=models.Sum("value")).get("total") or Decimal("0.00")
        comp_val = self.allocated_components.aggregate(total=models.Sum("value")).get("total") or Decimal("0.00")
        # Also include settlements where this heir is the recipient (original_owner)
        settlements_val = self.payments_expected.aggregate(total=models.Sum("amount")).get("total") or Decimal("0.00")
        return assets_val + comp_val + settlements_val

    def remaining_share(self):
        return max(self.share_value - self.real_allocated_value, 0)

    def can_select(self, amount):
        return amount <= self.remaining_share()

    def __str__(self):
        return f"{self.name} ({self.get_relationship_display()})"


class HeirAssetSelection(models.Model):
    class SelectionStatus(models.TextChoices):
        PENDING = "PENDING", _("قيد الانتظار")
        ACCEPTED = "ACCEPTED", _("مقبول")
        REJECTED = "REJECTED", _("مرفوض")

    heir = models.ForeignKey(Heir, on_delete=models.CASCADE, related_name="selections", verbose_name=_("الوريث"))
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="selection_intents", null=True, blank=True, verbose_name=_("الأصل"))
    component = models.ForeignKey("AssetComponent", on_delete=models.CASCADE, related_name="selection_intents", null=True, blank=True, verbose_name=_("جزء الأصل"))
    status = models.CharField(max_length=20, choices=SelectionStatus.choices, default=SelectionStatus.PENDING, verbose_name=_("حالة الاختيار"))
    selected_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name=_("القيمة المختارة"))
    requires_pledge = models.BooleanField(default=False, verbose_name=_("يتطلب تعهد مالي"))
    pledge_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name=_("مبلغ التعهد الاضافي"))
    is_challenging_owner = models.BooleanField(default=False, verbose_name=_("نزاع ضد مالك حالي"))
    is_processed = models.BooleanField(default=False, verbose_name=_("تم معالجته (تحويل لملكية أو نزاع)"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("heir", "asset", "component")
        verbose_name = _("رغبة اختيار أصل")
        verbose_name_plural = _("رغبات اختيار الأصول")

    def __str__(self):
        target = self.asset.description if self.asset else self.component.description
        return f"{self.heir.name} -> {target}"


class AssetComponent(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="components", verbose_name=_("الأصل التابع له"))
    parent_component = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='sub_components',
        verbose_name=_("المكون الأب")
    )
    description = models.CharField(max_length=255, verbose_name=_("وصف الجزء/العينة"))
    value = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("القيمة"))
    assigned_to = models.ForeignKey(Heir, on_delete=models.SET_NULL, null=True, blank=True, related_name="allocated_components", verbose_name=_("مخصص لـ"))
    is_sold_by_heir = models.BooleanField(default=False, verbose_name=_("مباع من قبل الوريث"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("جزء من الأصل")
        verbose_name_plural = _("أجزاء الأصول")

    @property
    def obligation_allocations_qs(self):
        return self.obligation_allocations.select_related("debt", "will_entry")

    @property
    def obligation_total(self):
        return self.obligation_allocations_qs.aggregate(total=models.Sum("allocated_amount")).get("total") or Decimal("0.00")

    @property
    def distributable_value(self):
        net_value = Decimal(str(self.value)) - Decimal(str(self.obligation_total))
        return net_value if net_value > 0 else Decimal("0.00")

    @property
    def has_obligation_burden(self):
        return self.obligation_total > 0

    @property
    def obligation_labels(self):
        return [allocation.obligation_label for allocation in self.obligation_allocations_qs]

    def __str__(self):
        return f"{self.description} ({self.value}) - {self.asset.description}"


class EstateObligationAllocation(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="obligation_allocations", verbose_name=_("القضية"))
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, null=True, blank=True, related_name="obligation_allocations", verbose_name=_("الدين"))
    will_entry = models.ForeignKey(Will, on_delete=models.CASCADE, null=True, blank=True, related_name="obligation_allocations", verbose_name=_("الوصية"))
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, null=True, blank=True, related_name="obligation_allocations", verbose_name=_("الأصل"))
    component = models.ForeignKey(AssetComponent, on_delete=models.CASCADE, null=True, blank=True, related_name="obligation_allocations", verbose_name=_("الجزء"))
    settlement = models.ForeignKey('PaymentSettlement', on_delete=models.SET_NULL, null=True, blank=True, related_name="obligation_allocations", verbose_name=_("التسوية المالية المرتبطة"))
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("القيمة المخصصة"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))

    class Meta:
        verbose_name = _("تخصيص دين أو وصية")
        verbose_name_plural = _("تخصيصات الديون والوصايا")

    @property
    def obligation_label(self):
        obligation = self.debt or self.will_entry
        kind = "دين" if self.debt_id else "وصية"
        return f"{kind}: {obligation.description}"

    @property
    def target_label(self):
        target = self.asset or self.component or self.settlement
        if target == self.settlement and target:
            return f"تسوية: {target.reason}"
        return target.description if target else "-"

    def __str__(self):
        obligation = self.debt or self.will_entry
        return f"{obligation} -> {self.target_label}"


class PublicAssetListing(models.Model):
    asset = models.OneToOneField(Asset, on_delete=models.CASCADE, null=True, blank=True, related_name="listing", verbose_name=_("الأصل الكامل"))
    component = models.OneToOneField(AssetComponent, on_delete=models.CASCADE, null=True, blank=True, related_name="listing", verbose_name=_("العينة/الجزء"))
    seller_name = models.CharField(max_length=255, verbose_name=_("اسم البائع"))
    seller_email = models.EmailField(verbose_name=_("البريد الإلكتروني"))
    seller_phone = models.CharField(max_length=20, verbose_name=_("رقم التواصل"))
    price = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("سعر العرض"))
    description = models.TextField(verbose_name=_("وصف العرض"))
    image = models.ImageField(upload_to="listings/", null=True, blank=True, verbose_name=_("صورة خاصة للعرض"))
    is_active = models.BooleanField(default=True, verbose_name=_("نشط (يُعرض للبيع)"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ العرض"))

    class Meta:
        verbose_name = _("عرض بيع أصل (عام)")
        verbose_name_plural = _("عروض بيع الأصول (عامة)")

    def __str__(self):
        item_desc = self.asset.description if self.asset else self.component.description if self.component else "N/A"
        return f"{self.seller_name} - {item_desc}"


class DisputeRaffle(models.Model):
    class DisputeSource(models.TextChoices):
        MUTUAL_CONSENT = "MUTUAL_CONSENT", _("حالة التراضي")
        PARTIAL_OBJECTION = "PARTIAL_OBJECTION", _("الاعتراض الجزئي باختيار التركة")

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="disputes", verbose_name=_("القضية"))
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("الأصل المتنازع عليه"))
    component = models.ForeignKey(AssetComponent, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("الجزء المتنازع عليه"))
    contenders = models.ManyToManyField(Heir, related_name="raffle_entries", verbose_name=_("المتنازعين"))
    winner = models.ForeignKey(Heir, on_delete=models.SET_NULL, null=True, blank=True, related_name="won_raffles", verbose_name=_("الفائز بالقرعة"))
    is_resolved = models.BooleanField(default=False, verbose_name=_("تم حل النزاع (إجراء القرعة)"))
    source = models.CharField(max_length=30, choices=DisputeSource.choices, default=DisputeSource.MUTUAL_CONSENT, verbose_name=_("مصدر النزاع"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("نزاع / قرعة")
        verbose_name_plural = _("النزاعات والقرعات")

    def __str__(self):
        target = self.asset.description if self.asset else self.component.description
        return f"قرعة في قضية {self.case.display_case_number} على {target}"


class PaymentSettlement(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="settlements", verbose_name=_("القضية"))
    payer = models.ForeignKey(Heir, on_delete=models.CASCADE, related_name="payments_owed", verbose_name=_("الدافع (المتعهد)"))
    original_owner = models.ForeignKey(Heir, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments_expected", verbose_name=_("المستلم الأصلي (إن وجد)"))
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("الأصل المرتبط"))
    component = models.ForeignKey(AssetComponent, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("الجزء المرتبط"))
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("المبلغ"))
    heir_confirmed_payment = models.BooleanField(default=False, verbose_name=_("قام الوريث بتأكيد السداد"))
    receiver_confirmed_payment = models.BooleanField(default=False, verbose_name=_("قام المستلم بتأكيد الاستلام"))
    is_paid_to_judge = models.BooleanField(default=False, verbose_name=_("تم استلام المبلغ من قبل القاضي"))
    is_delivered_to_owner = models.BooleanField(default=False, verbose_name=_("تم تسليم المبلغ للمالك النهائي"))
    reason = models.CharField(max_length=255, verbose_name=_("سبب الدفعة (فرق قيمة، تعويض نزاع)"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("تسوية مالية")
        verbose_name_plural = _("التسويات المالية")

    def __str__(self):
        return f"دفعة من {self.payer.name} بقيمة {self.amount}"


class ComponentConflictRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("قيد المراجعة من الوريث1")
        ACCEPTED = "ACCEPTED", _("موافق (تم التنازل)")
        RAFFLE_REQUIRED = "RAFFLE_REQUIRED", _("مرفوض (طلب قرعة)")
        CANCELED = "CANCELED", _("ملغي (تم التنازل لطرف آخر)")

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="component_conflicts", verbose_name=_("القضية"))
    parent_asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="conflicts", verbose_name=_("الأصل المتنازع عليه"))
    component = models.ForeignKey(AssetComponent, on_delete=models.CASCADE, null=True, blank=True, related_name="conflicts", verbose_name=_("العينة المطلوبة"))
    is_full_asset = models.BooleanField(default=False, verbose_name=_("نزاع على أصل كامل"))
    owner_heir = models.ForeignKey(Heir, on_delete=models.CASCADE, related_name="received_conflicts", verbose_name=_("صاحب الأصل الأساسي (وريث 1)"))
    requesting_heir = models.ForeignKey(Heir, on_delete=models.CASCADE, related_name="initiated_conflicts", verbose_name=_("طالب العينة (وريث 2)"))
    triggered_by_individual_rejection = models.BooleanField(default=False, verbose_name=_("ناتج عن رفض فردي"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name=_("حالة الطلب"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("طلب نزاع على عينة")
        verbose_name_plural = _("طلبات النزاع على العينات")
        unique_together = ("parent_asset", "component", "requesting_heir")

    def __str__(self):
        target = self.component.description if self.component else self.parent_asset.description
        return f"نزاع {self.requesting_heir.name} على {target}"


class SelectionLog(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="selection_logs", verbose_name=_("القضية"))
    heir = models.ForeignKey(Heir, on_delete=models.CASCADE, verbose_name=_("الوريث"))
    action_text = models.TextField(verbose_name=_("نص الإجراء"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("وقت الإجراء"))

    class Meta:
        verbose_name = _("سجل اختيار أصل")
        verbose_name_plural = _("سجلات اختيار الأصول")
        ordering = ["-created_at"]


class AllocationProposal(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("بانتظار موافقة الوريث")
        ACCEPTED = "ACCEPTED", _("مقبول من الوريث")
        REJECTED = "REJECTED", _("مرفوض من الوريث")

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="allocation_proposals", verbose_name=_("القضية"))
    heir = models.ForeignKey(Heir, on_delete=models.CASCADE, related_name="allocation_proposals", verbose_name=_("الوريث المستهدف"))
    assets = models.ManyToManyField(Asset, blank=True, verbose_name=_("الأصول المقترحة"))
    components = models.ManyToManyField(AssetComponent, blank=True, verbose_name=_("العينات المقترحة"))
    selected_settlement_ids = models.TextField(blank=True, null=True, verbose_name=_("معرفات التسويات المختارة"))
    difference_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_("مبلغ الفرق للدفع"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name=_("حالة الطلب"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الطلب"))

    class Meta:
        verbose_name = _("مقترح توزيع (بانتظار إقرار)")
        verbose_name_plural = _("مقترحات التوزيع")

    def __str__(self):
        return f"مقترح لـ {self.heir.name} - فرق: {self.difference_amount}"


class CaseAuditLog(models.Model):
    class ActionType(models.TextChoices):
        CASE_OPENED = "CASE_OPENED", _("فتح القضية")
        INFO_UPDATED = "INFO_UPDATED", _("تحديث بيانات")
        ASSET_ADDED = "ASSET_ADDED", _("إضافة أصل")
        HEIR_ADDED = "HEIR_ADDED", _("إضافة وريث")
        PORTAL_OPENED = "PORTAL_OPENED", _("فتح بوابة الاختيار")
        PORTAL_CLOSED = "PORTAL_CLOSED", _("إغلاق بوابة الاختيار")
        HEIR_SELECTION = "HEIR_SELECTION", _("اختيار وريث")
        JUDGE_DECISION = "JUDGE_DECISION", _("قرار قاضٍ (قبول/رفض)")
        RAFFLE_RESULT = "RAFFLE_RESULT", _("نتيجة قرعة")
        PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED", _("تأكيد سداد نقدي")
        FINAL_REPORT = "FINAL_REPORT", _("اعتماد محضر القسمة النهائي")
        OTHER = "OTHER", _("إجراء آخر")

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="audit_logs", verbose_name=_("القضية"))
    action = models.CharField(max_length=50, choices=ActionType.choices, verbose_name=_("نوع الإجراء"))
    description = models.TextField(verbose_name=_("تفاصيل الإجراء"))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("المستخدم"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ ووقت الإجراء"))

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("سجل القضية")
        verbose_name_plural = _("سجلات القضايا")

    def __str__(self):
        return f"{self.case.display_case_number} - {self.get_action_display()} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
