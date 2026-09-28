import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage

PRIVATE_STORAGE = FileSystemStorage(location=Path(settings.BASE_DIR) / 'private_uploads')
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.pdf', '.txt', '.csv', '.xlsx', '.xls', '.docx', '.pptx', '.zip'}
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024


def validate_attachment(upload):
    if Path(upload.name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValidationError('Неподдържан файлов формат.')
    if upload.size > MAX_ATTACHMENT_SIZE:
        raise ValidationError('Файлът трябва да е до 20 MB.')


def attachment_path(instance, filename):
    return f'tasks/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'
