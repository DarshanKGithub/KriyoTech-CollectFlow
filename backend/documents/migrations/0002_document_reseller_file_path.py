from django.db import migrations, models
import documents.models


class Migration(migrations.Migration):
    dependencies = [("documents", "0001_initial")]
    operations = [migrations.AlterField(model_name="document", name="file",
        field=models.FileField(max_length=512, upload_to=documents.models.tenant_document_path))]
