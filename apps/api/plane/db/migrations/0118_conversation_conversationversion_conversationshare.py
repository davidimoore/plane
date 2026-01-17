# Generated migration for Conversation models

import secrets
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


def generate_share_token():
    return secrets.token_urlsafe(32)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("db", "0117_exporterhistory_progress_tracking"),
    ]

    operations = [
        migrations.CreateModel(
            name="Conversation",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Created At"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Last Modified At"
                    ),
                ),
                (
                    "id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "name",
                    models.TextField(blank=True, default="Untitled Conversation"),
                ),
                (
                    "description",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "description_binary",
                    models.BinaryField(null=True),
                ),
                (
                    "description_html",
                    models.TextField(blank=True, default="<p></p>"),
                ),
                (
                    "description_stripped",
                    models.TextField(blank=True, null=True),
                ),
                (
                    "access",
                    models.PositiveSmallIntegerField(
                        choices=[(0, "Public"), (1, "Private")],
                        default=1,
                    ),
                ),
                (
                    "share_token",
                    models.CharField(
                        default=generate_share_token,
                        max_length=64,
                        unique=True,
                    ),
                ),
                (
                    "is_shared",
                    models.BooleanField(default=False),
                ),
                (
                    "share_expires_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "archived_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_created_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created By",
                    ),
                ),
                (
                    "owned_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_updated_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Last Modified By",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversations",
                        to="db.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Conversation",
                "verbose_name_plural": "Conversations",
                "db_table": "conversations",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="ConversationVersion",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Created At"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Last Modified At"
                    ),
                ),
                (
                    "id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "version_number",
                    models.PositiveIntegerField(default=1),
                ),
                (
                    "name",
                    models.TextField(blank=True),
                ),
                (
                    "description",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "description_binary",
                    models.BinaryField(null=True),
                ),
                (
                    "description_html",
                    models.TextField(blank=True, default="<p></p>"),
                ),
                (
                    "description_stripped",
                    models.TextField(blank=True, null=True),
                ),
                (
                    "description_json",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "last_saved_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "label",
                    models.CharField(blank=True, max_length=255),
                ),
                (
                    "change_summary",
                    models.TextField(blank=True),
                ),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="db.conversation",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_created_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created By",
                    ),
                ),
                (
                    "owned_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversation_versions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_updated_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Last Modified By",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversation_versions",
                        to="db.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Conversation Version",
                "verbose_name_plural": "Conversation Versions",
                "db_table": "conversation_versions",
                "ordering": ("-version_number", "-created_at"),
                "unique_together": {("conversation", "version_number")},
            },
        ),
        migrations.CreateModel(
            name="ConversationShare",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Created At"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Last Modified At"
                    ),
                ),
                (
                    "id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "email",
                    models.EmailField(blank=True, max_length=254, null=True),
                ),
                (
                    "permission",
                    models.PositiveSmallIntegerField(
                        choices=[(0, "Viewer"), (1, "Commenter"), (2, "Editor")],
                        default=0,
                    ),
                ),
                (
                    "invite_token",
                    models.CharField(
                        default=generate_share_token,
                        max_length=64,
                        unique=True,
                    ),
                ),
                (
                    "accepted",
                    models.BooleanField(default=False),
                ),
                (
                    "accepted_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "expires_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shares",
                        to="db.conversation",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_created_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created By",
                    ),
                ),
                (
                    "shared_with",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shared_conversations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_updated_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Last Modified By",
                    ),
                ),
            ],
            options={
                "verbose_name": "Conversation Share",
                "verbose_name_plural": "Conversation Shares",
                "db_table": "conversation_shares",
                "ordering": ("-created_at",),
                "unique_together": {("conversation", "shared_with")},
            },
        ),
    ]
