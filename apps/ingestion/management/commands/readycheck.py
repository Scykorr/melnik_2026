from django.core.management.base import BaseCommand, CommandError

from apps.common.health import ready


class Command(BaseCommand):
    help = "Проверяет готовность базы и кэша."

    def handle(self, *args, **options):
        response = ready(None)
        if response.status_code != 200:
            raise CommandError("Приложение не готово")
        self.stdout.write(self.style.SUCCESS("ready"))
