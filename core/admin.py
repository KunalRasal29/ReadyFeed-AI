from django.contrib import admin

from core.models import (
    CommuteWindow,
    ContentSource,
    DownloadItem,
    Subscription,
    UserPreference,
)


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "max_daily_items", "max_storage_mb", "updated_at")
    search_fields = ("user__username", "user__email")


@admin.register(ContentSource)
class ContentSourceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "type",
        "policy",
        "license_name",
        "attribution_required",
        "is_active",
        "created_at",
    )
    list_filter = ("type", "policy", "license_name", "attribution_required", "is_active")
    search_fields = ("name", "feed_url", "license_name", "usage_notes")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "source", "priority", "is_active", "created_at")
    list_filter = ("is_active", "priority")
    search_fields = ("user__username", "source__name")


@admin.register(DownloadItem)
class DownloadItemAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "source", "status", "available_from")
    list_filter = ("status", "source__type")
    search_fields = ("title", "description", "user__username", "source__name")


@admin.register(CommuteWindow)
class CommuteWindowAdmin(admin.ModelAdmin):
    list_display = ("label", "user", "start_time", "end_time", "is_active")
    list_filter = ("is_active",)
    search_fields = ("label", "user__username")
