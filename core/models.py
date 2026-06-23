from django.conf import settings
from django.db import models
from django.utils import timezone


class UserPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preference",
    )
    topics = models.JSONField(default=list, blank=True)
    max_daily_items = models.IntegerField(default=10)
    max_storage_mb = models.IntegerField(default=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences for {self.user}"


class ContentSource(models.Model):
    TYPE_PODCAST = "podcast"
    TYPE_ARTICLE = "article"
    TYPE_VIDEO = "video"
    TYPE_MEME = "meme"
    TYPE_NEWS = "news"
    TYPE_IMAGE = "image"
    TYPE_BOOK = "book"
    TYPE_CHOICES = [
        (TYPE_PODCAST, "Podcast"),
        (TYPE_ARTICLE, "Article"),
        (TYPE_VIDEO, "Video"),
        (TYPE_MEME, "Meme"),
        (TYPE_NEWS, "News"),
        (TYPE_IMAGE, "Image"),
        (TYPE_BOOK, "Book"),
    ]

    POLICY_METADATA_ONLY = "metadata_only"
    POLICY_CACHE_ALLOWED = "cache_allowed"
    POLICY_CHOICES = [
        (POLICY_METADATA_ONLY, "Metadata only"),
        (POLICY_CACHE_ALLOWED, "Cache allowed"),
    ]

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    feed_url = models.URLField(max_length=500)
    policy = models.CharField(
        max_length=20,
        choices=POLICY_CHOICES,
        default=POLICY_METADATA_ONLY,
    )
    is_active = models.BooleanField(default=True)
    license_name = models.CharField(max_length=120, blank=True)
    license_url = models.URLField(max_length=500, blank=True)
    attribution_required = models.BooleanField(default=False)
    usage_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Subscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    source = models.ForeignKey(
        ContentSource,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    priority = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "source")
        ordering = ["priority", "source__name"]

    def __str__(self):
        return f"{self.user} -> {self.source}"


class DownloadItem(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_DOWNLOADING = "downloading"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_DOWNLOADING, "Downloading"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="downloads",
    )
    source = models.ForeignKey(
        ContentSource,
        on_delete=models.CASCADE,
        related_name="downloads",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    original_url = models.URLField(max_length=1000)
    media_url = models.URLField(max_length=1000, blank=True)
    local_file_path = models.CharField(max_length=1000, blank=True)
    file_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
    )
    available_from = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-available_from", "-created_at"]

    def __str__(self):
        return self.title


class CommuteWindow(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="commute_windows",
    )
    label = models.CharField(max_length=100)
    start_time = models.TimeField()
    end_time = models.TimeField()
    days_of_week = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_time", "label"]

    def __str__(self):
        return f"{self.label} ({self.user})"
