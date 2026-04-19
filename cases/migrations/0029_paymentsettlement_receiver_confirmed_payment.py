from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0028_case_sequence_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentsettlement",
            name="receiver_confirmed_payment",
            field=models.BooleanField(default=False, verbose_name="قام المستلم بتأكيد الاستلام"),
        ),
    ]
