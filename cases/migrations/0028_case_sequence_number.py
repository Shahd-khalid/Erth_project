from django.db import migrations, models


def populate_case_sequences(apps, schema_editor):
    Case = apps.get_model("cases", "Case")
    db_alias = schema_editor.connection.alias

    judge_ids = (
        Case.objects.using(db_alias)
        .order_by()
        .values_list("judge_id", flat=True)
        .distinct()
    )

    for judge_id in judge_ids:
        cases = Case.objects.using(db_alias).filter(judge_id=judge_id).order_by("created_at", "id")
        for sequence, case in enumerate(cases, start=1):
            case.sequence_number = sequence
            case.case_number = str(sequence)
            case.save(update_fields=["sequence_number", "case_number"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0027_heir_is_judge_confirmed"),
    ]

    operations = [
        migrations.AddField(
            model_name="case",
            name="sequence_number",
            field=models.PositiveIntegerField(blank=True, editable=False, null=True, verbose_name="الرقم التسلسلي للقضية"),
        ),
        migrations.RunPython(populate_case_sequences, noop_reverse),
        migrations.AddConstraint(
            model_name="case",
            constraint=models.UniqueConstraint(fields=("judge", "sequence_number"), name="unique_case_sequence_per_judge"),
        ),
    ]
