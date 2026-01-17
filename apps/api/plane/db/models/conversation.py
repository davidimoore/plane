import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from plane.utils.html_processor import strip_tags

from .base import BaseModel


def generate_share_token():
    """Generate a unique share token for conversations."""
    return secrets.token_urlsafe(32)


class Conversation(BaseModel):
    """
    Model to store conversations that can be shared and versioned.
    Follows the Page model pattern for access control and content storage.
    """

    PRIVATE_ACCESS = 1
    PUBLIC_ACCESS = 0

    ACCESS_CHOICES = (
        (PUBLIC_ACCESS, "Public"),
        (PRIVATE_ACCESS, "Private"),
    )

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    name = models.TextField(blank=True, default="Untitled Conversation")
    description = models.JSONField(default=dict, blank=True)
    description_binary = models.BinaryField(null=True)
    description_html = models.TextField(blank=True, default="<p></p>")
    description_stripped = models.TextField(blank=True, null=True)
    owned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    access = models.PositiveSmallIntegerField(
        choices=ACCESS_CHOICES,
        default=PRIVATE_ACCESS,
    )
    # Share token for public sharing without authentication
    share_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_share_token,
    )
    # Whether the conversation is currently shared via token
    is_shared = models.BooleanField(default=False)
    # Optional expiry for shared links
    share_expires_at = models.DateTimeField(null=True, blank=True)
    # Metadata for the conversation
    metadata = models.JSONField(default=dict, blank=True)
    # Archived status
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"
        db_table = "conversations"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.owned_by.email} <{self.name}>"

    def save(self, *args, **kwargs):
        # Strip the html tags using html parser
        self.description_stripped = (
            None
            if (self.description_html == "" or self.description_html is None)
            else strip_tags(self.description_html)
        )
        super(Conversation, self).save(*args, **kwargs)

    def regenerate_share_token(self):
        """Regenerate the share token for security purposes."""
        self.share_token = generate_share_token()
        self.save(update_fields=["share_token"])
        return self.share_token

    def is_share_valid(self):
        """Check if the share link is still valid."""
        if not self.is_shared:
            return False
        if self.share_expires_at and timezone.now() > self.share_expires_at:
            return False
        return True


class ConversationVersion(BaseModel):
    """
    Model to store versions of conversations.
    Each version represents a snapshot of the conversation at a point in time.
    Follows the PageVersion model pattern.
    """

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="conversation_versions",
    )
    conversation = models.ForeignKey(
        "db.Conversation",
        on_delete=models.CASCADE,
        related_name="versions",
    )
    owned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_versions",
    )
    # Version metadata
    version_number = models.PositiveIntegerField(default=1)
    name = models.TextField(blank=True)
    # Content fields - same as Conversation
    description = models.JSONField(default=dict, blank=True)
    description_binary = models.BinaryField(null=True)
    description_html = models.TextField(blank=True, default="<p></p>")
    description_stripped = models.TextField(blank=True, null=True)
    description_json = models.JSONField(default=dict, blank=True)
    # Snapshot of metadata at version time
    metadata = models.JSONField(default=dict, blank=True)
    # When this version was saved
    last_saved_at = models.DateTimeField(default=timezone.now)
    # Optional label/tag for this version
    label = models.CharField(max_length=255, blank=True)
    # Change summary
    change_summary = models.TextField(blank=True)

    class Meta:
        verbose_name = "Conversation Version"
        verbose_name_plural = "Conversation Versions"
        db_table = "conversation_versions"
        ordering = ("-version_number", "-created_at")
        unique_together = ["conversation", "version_number"]

    def __str__(self):
        return f"{self.conversation.name} v{self.version_number}"

    def save(self, *args, **kwargs):
        # Strip the html tags using html parser
        self.description_stripped = (
            None
            if (self.description_html == "" or self.description_html is None)
            else strip_tags(self.description_html)
        )
        # Auto-increment version number if not set
        if not self.version_number:
            last_version = ConversationVersion.objects.filter(
                conversation=self.conversation
            ).order_by("-version_number").first()
            self.version_number = (last_version.version_number + 1) if last_version else 1
        super(ConversationVersion, self).save(*args, **kwargs)

    @classmethod
    def create_version(cls, conversation, user, label="", change_summary=""):
        """
        Create a new version from the current state of a conversation.
        """
        return cls.objects.create(
            workspace=conversation.workspace,
            conversation=conversation,
            owned_by=user,
            name=conversation.name,
            description=conversation.description,
            description_binary=conversation.description_binary,
            description_html=conversation.description_html,
            description_stripped=conversation.description_stripped,
            metadata=conversation.metadata,
            label=label,
            change_summary=change_summary,
        )


class ConversationShare(BaseModel):
    """
    Model to track individual share invitations for conversations.
    Allows sharing with specific users or via email invitation.
    """

    VIEWER = 0
    COMMENTER = 1
    EDITOR = 2

    PERMISSION_CHOICES = (
        (VIEWER, "Viewer"),
        (COMMENTER, "Commenter"),
        (EDITOR, "Editor"),
    )

    conversation = models.ForeignKey(
        "db.Conversation",
        on_delete=models.CASCADE,
        related_name="shares",
    )
    # Either shared with a user or via email
    shared_with = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shared_conversations",
        null=True,
        blank=True,
    )
    email = models.EmailField(null=True, blank=True)
    # Permission level
    permission = models.PositiveSmallIntegerField(
        choices=PERMISSION_CHOICES,
        default=VIEWER,
    )
    # Invitation token for email shares
    invite_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_share_token,
    )
    # Whether the invitation has been accepted
    accepted = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)
    # Expiry for the invitation
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Conversation Share"
        verbose_name_plural = "Conversation Shares"
        db_table = "conversation_shares"
        ordering = ("-created_at",)
        # Ensure a user can only have one share record per conversation
        unique_together = ["conversation", "shared_with"]

    def __str__(self):
        target = self.shared_with.email if self.shared_with else self.email
        return f"{self.conversation.name} shared with {target}"

    def is_valid(self):
        """Check if the share invitation is still valid."""
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True
