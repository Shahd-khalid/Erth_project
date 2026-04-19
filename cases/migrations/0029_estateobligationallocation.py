from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0028_case_sequence_number"),
    ]

    operations = [
        migrations.CreateModel(
            name="EstateObligationAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("allocated_amount", models.DecimalField(decimal_places=2, max_digits=15, verbose_name="القيمة المخصصة")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("asset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="obligation_allocations", to="cases.asset", verbose_name="الأصل")),
                ("case", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="obligation_allocations", to="cases.case", verbose_name="القضية")),
                ("component", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="obligation_allocations", to="cases.assetcomponent", verbose_name="الجزء")),
                ("debt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="obligation_allocations", to="cases.debt", verbose_name="الدين")),
                ("will_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="obligation_allocations", to="cases.will", verbose_name="الوصية")),
            ],
            options={
                "verbose_name": "تخصيص دين أو وصية",
                "verbose_name_plural": "تخصيصات الديون والوصايا",
            },
        ),
    ]
