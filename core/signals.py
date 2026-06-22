from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import UserPreference


@receiver(post_save, sender=get_user_model())
def create_user_preference(sender, instance, created, **kwargs):
    if created:
        UserPreference.objects.get_or_create(user=instance)
