from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

from core.ingestion.adapters import supports_source_discovery
from core.models import (
    CommuteWindow,
    ContentSource,
    DownloadItem,
    Subscription,
    UserPreference,
)
from core.offline_storage import OfflineStorageError, offline_file_url


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]
        read_only_fields = ["id"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]
        read_only_fields = ["id"]
        extra_kwargs = {
            "email": {"required": False, "allow_blank": True},
        }

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs.get("username"),
            password=attrs.get("password"),
        )
        if user is None:
            raise serializers.ValidationError("Invalid username or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        attrs["user"] = user
        return attrs


class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = [
            "id",
            "user",
            "topics",
            "max_daily_items",
            "max_storage_mb",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]


class ContentSourceSerializer(serializers.ModelSerializer):
    supports_discovery = serializers.SerializerMethodField()

    class Meta:
        model = ContentSource
        fields = [
            "id",
            "name",
            "type",
            "feed_url",
            "policy",
            "is_active",
            "license_name",
            "license_url",
            "attribution_required",
            "usage_notes",
            "supports_discovery",
            "created_at",
        ]
        read_only_fields = ["id", "supports_discovery", "created_at"]

    def get_supports_discovery(self, obj):
        return obj.policy == ContentSource.POLICY_CACHE_ALLOWED and supports_source_discovery(obj)


class SubscriptionSerializer(serializers.ModelSerializer):
    source_detail = ContentSourceSerializer(source="source", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "user",
            "source",
            "source_detail",
            "priority",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "user", "source_detail", "created_at"]
        validators = []

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None
        source = attrs.get("source") or getattr(self.instance, "source", None)

        if user and source:
            existing = Subscription.objects.filter(user=user, source=source)
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    "You are already subscribed to this source."
                )
        return attrs


class DownloadItemSerializer(serializers.ModelSerializer):
    source_detail = ContentSourceSerializer(source="source", read_only=True)
    local_file_url = serializers.SerializerMethodField()
    offline_file_url = serializers.SerializerMethodField()

    class Meta:
        model = DownloadItem
        fields = [
            "id",
            "user",
            "source",
            "source_detail",
            "title",
            "description",
            "original_url",
            "media_url",
            "local_file_path",
            "local_file_url",
            "offline_file_url",
            "storage_backend",
            "storage_key",
            "file_size_bytes",
            "error_message",
            "status",
            "available_from",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "source_detail",
            "local_file_path",
            "local_file_url",
            "offline_file_url",
            "storage_backend",
            "storage_key",
            "file_size_bytes",
            "error_message",
            "status",
            "created_at",
            "updated_at",
        ]

    def get_local_file_url(self, obj):
        return self.get_offline_file_url(obj)

    def get_offline_file_url(self, obj):
        try:
            return offline_file_url(obj, request=self.context.get("request"))
        except OfflineStorageError:
            return ""


class CommuteWindowSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommuteWindow
        fields = [
            "id",
            "user",
            "label",
            "start_time",
            "end_time",
            "days_of_week",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "user", "created_at"]
