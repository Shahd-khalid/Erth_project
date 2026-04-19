from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0029_estateobligationallocation"),
    ]

    operations = [
        migrations.AddField(
            model_name="componentconflictrequest",
            name="triggered_by_individual_rejection",
            field=models.BooleanField(default=False, verbose_name="ناتج عن رفض فردي"),
        ),
    ]
