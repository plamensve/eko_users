from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_alter_card_options_alter_company_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="price",
            name="final_price",
            field=models.DecimalField(decimal_places=6, max_digits=12, verbose_name="Крайна цена"),
        ),
        migrations.AlterField(
            model_name="price",
            name="eko_price",
            field=models.DecimalField(decimal_places=6, default=0, max_digits=12, verbose_name="ЕКО цена"),
        ),
        migrations.AlterField(
            model_name="price",
            name="margin",
            field=models.DecimalField(decimal_places=6, default=0, max_digits=12, verbose_name="Марж"),
        ),
        migrations.AlterField(
            model_name="price",
            name="discount",
            field=models.DecimalField(decimal_places=6, default=0, max_digits=12, verbose_name="Отстъпка"),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="bill_qty",
            field=models.DecimalField(decimal_places=6, max_digits=14, verbose_name="Количество"),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="price",
            field=models.DecimalField(decimal_places=6, max_digits=12, verbose_name="ЕКО цена"),
        ),
    ]
