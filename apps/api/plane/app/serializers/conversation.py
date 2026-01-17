# Third party imports
from rest_framework import serializers
import base64

# Module imports
from .base import BaseSerializer
from plane.utils.content_validator import (
    validate_binary_data,
    validate_html_content,
)
from plane.db.models import (
    Conversation,
    ConversationVersion,
    ConversationShare,
    User,
)


class ConversationSerializer(BaseSerializer):
    """Serializer for Conversation list view."""

    owner_detail = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "name",
            "owned_by",
            "owner_detail",
            "access",
            "is_shared",
            "share_expires_at",
            "archived_at",
            "workspace",
            "metadata",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "version_count",
        ]
        read_only_fields = ["workspace", "owned_by", "share_token"]

    def get_owner_detail(self, obj):
        if obj.owned_by:
            return {
                "id": str(obj.owned_by.id),
                "email": obj.owned_by.email,
                "first_name": obj.owned_by.first_name,
                "last_name": obj.owned_by.last_name,
            }
        return None

    def get_version_count(self, obj):
        return obj.versions.count()


class ConversationDetailSerializer(ConversationSerializer):
    """Serializer for Conversation detail view with full content."""

    description_html = serializers.CharField(required=False, allow_blank=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + [
            "description",
            "description_html",
        ]


class ConversationCreateSerializer(BaseSerializer):
    """Serializer for creating a Conversation."""

    description_binary = serializers.CharField(required=False, allow_blank=True)
    description_html = serializers.CharField(required=False, allow_blank=True)
    description = serializers.JSONField(required=False, default=dict)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "name",
            "access",
            "metadata",
            "description",
            "description_binary",
            "description_html",
        ]

    def validate_description_binary(self, value):
        """Validate the base64-encoded binary data."""
        if not value:
            return None

        try:
            binary_data = base64.b64decode(value)
            is_valid, error_message = validate_binary_data(binary_data)
            if not is_valid:
                raise serializers.ValidationError(f"Invalid binary data: {error_message}")
            return binary_data
        except Exception as e:
            if isinstance(e, serializers.ValidationError):
                raise
            raise serializers.ValidationError("Failed to decode base64 data")

    def validate_description_html(self, value):
        """Validate the HTML content."""
        if not value:
            return value

        is_valid, error_message, sanitized_html = validate_html_content(value)
        if not is_valid:
            raise serializers.ValidationError(error_message)

        return sanitized_html if sanitized_html is not None else value

    def create(self, validated_data):
        workspace_id = self.context.get("workspace_id")
        owned_by_id = self.context.get("owned_by_id")

        return Conversation.objects.create(
            **validated_data,
            workspace_id=workspace_id,
            owned_by_id=owned_by_id,
        )


class ConversationUpdateSerializer(BaseSerializer):
    """Serializer for updating a Conversation."""

    description_binary = serializers.CharField(required=False, allow_blank=True)
    description_html = serializers.CharField(required=False, allow_blank=True)
    description = serializers.JSONField(required=False)

    class Meta:
        model = Conversation
        fields = [
            "name",
            "access",
            "is_shared",
            "share_expires_at",
            "archived_at",
            "metadata",
            "description",
            "description_binary",
            "description_html",
        ]

    def validate_description_binary(self, value):
        """Validate the base64-encoded binary data."""
        if not value:
            return None

        try:
            binary_data = base64.b64decode(value)
            is_valid, error_message = validate_binary_data(binary_data)
            if not is_valid:
                raise serializers.ValidationError(f"Invalid binary data: {error_message}")
            return binary_data
        except Exception as e:
            if isinstance(e, serializers.ValidationError):
                raise
            raise serializers.ValidationError("Failed to decode base64 data")

    def validate_description_html(self, value):
        """Validate the HTML content."""
        if not value:
            return value

        is_valid, error_message, sanitized_html = validate_html_content(value)
        if not is_valid:
            raise serializers.ValidationError(error_message)

        return sanitized_html if sanitized_html is not None else value


class ConversationVersionSerializer(BaseSerializer):
    """Serializer for ConversationVersion list view."""

    owner_detail = serializers.SerializerMethodField()

    class Meta:
        model = ConversationVersion
        fields = [
            "id",
            "conversation",
            "workspace",
            "version_number",
            "name",
            "label",
            "change_summary",
            "last_saved_at",
            "owned_by",
            "owner_detail",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["workspace", "conversation", "version_number"]

    def get_owner_detail(self, obj):
        if obj.owned_by:
            return {
                "id": str(obj.owned_by.id),
                "email": obj.owned_by.email,
                "first_name": obj.owned_by.first_name,
                "last_name": obj.owned_by.last_name,
            }
        return None


class ConversationVersionDetailSerializer(BaseSerializer):
    """Serializer for ConversationVersion detail view with full content."""

    owner_detail = serializers.SerializerMethodField()

    class Meta:
        model = ConversationVersion
        fields = [
            "id",
            "conversation",
            "workspace",
            "version_number",
            "name",
            "label",
            "change_summary",
            "description",
            "description_binary",
            "description_html",
            "description_json",
            "metadata",
            "last_saved_at",
            "owned_by",
            "owner_detail",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["workspace", "conversation", "version_number"]

    def get_owner_detail(self, obj):
        if obj.owned_by:
            return {
                "id": str(obj.owned_by.id),
                "email": obj.owned_by.email,
                "first_name": obj.owned_by.first_name,
                "last_name": obj.owned_by.last_name,
            }
        return None


class ConversationVersionCreateSerializer(BaseSerializer):
    """Serializer for creating a ConversationVersion."""

    class Meta:
        model = ConversationVersion
        fields = [
            "label",
            "change_summary",
        ]

    def create(self, validated_data):
        conversation = self.context.get("conversation")
        user = self.context.get("user")

        return ConversationVersion.create_version(
            conversation=conversation,
            user=user,
            label=validated_data.get("label", ""),
            change_summary=validated_data.get("change_summary", ""),
        )


class ConversationShareSerializer(BaseSerializer):
    """Serializer for ConversationShare."""

    shared_with_detail = serializers.SerializerMethodField()

    class Meta:
        model = ConversationShare
        fields = [
            "id",
            "conversation",
            "shared_with",
            "shared_with_detail",
            "email",
            "permission",
            "accepted",
            "accepted_at",
            "expires_at",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = ["conversation", "invite_token", "accepted", "accepted_at"]

    def get_shared_with_detail(self, obj):
        if obj.shared_with:
            return {
                "id": str(obj.shared_with.id),
                "email": obj.shared_with.email,
                "first_name": obj.shared_with.first_name,
                "last_name": obj.shared_with.last_name,
            }
        return None


class ConversationShareCreateSerializer(BaseSerializer):
    """Serializer for creating a ConversationShare."""

    shared_with = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )
    email = serializers.EmailField(required=False, allow_null=True)

    class Meta:
        model = ConversationShare
        fields = [
            "shared_with",
            "email",
            "permission",
            "expires_at",
        ]

    def validate(self, data):
        # Must provide either shared_with or email
        if not data.get("shared_with") and not data.get("email"):
            raise serializers.ValidationError(
                "Either 'shared_with' (user ID) or 'email' must be provided."
            )
        return data

    def create(self, validated_data):
        conversation = self.context.get("conversation")

        return ConversationShare.objects.create(
            conversation=conversation,
            **validated_data,
        )


class PublicConversationSerializer(BaseSerializer):
    """Serializer for public/shared conversation view (limited fields)."""

    owner_detail = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "name",
            "description",
            "description_html",
            "owner_detail",
            "created_at",
            "updated_at",
        ]

    def get_owner_detail(self, obj):
        if obj.owned_by:
            return {
                "first_name": obj.owned_by.first_name,
                "last_name": obj.owned_by.last_name,
            }
        return None


class PublicConversationVersionSerializer(BaseSerializer):
    """Serializer for public conversation version view (limited fields)."""

    class Meta:
        model = ConversationVersion
        fields = [
            "id",
            "version_number",
            "name",
            "description",
            "description_html",
            "label",
            "last_saved_at",
            "created_at",
        ]
