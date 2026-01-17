import pytest
from django.utils import timezone
from datetime import timedelta

from plane.db.models import Conversation, ConversationVersion, ConversationShare


@pytest.mark.unit
class TestConversationModel:
    """Tests for the Conversation model."""

    @pytest.mark.django_db
    def test_conversation_creation(self, workspace, create_user):
        """Test creating a conversation."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Test Conversation",
            access=Conversation.PRIVATE_ACCESS,
        )

        assert conversation.id is not None
        assert conversation.name == "Test Conversation"
        assert conversation.access == Conversation.PRIVATE_ACCESS
        assert conversation.owned_by == create_user
        assert conversation.workspace == workspace
        assert conversation.is_shared is False
        assert conversation.share_token is not None

    @pytest.mark.django_db
    def test_conversation_default_values(self, workspace, create_user):
        """Test that default values are set correctly."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
        )

        assert conversation.name == "Untitled Conversation"
        assert conversation.access == Conversation.PRIVATE_ACCESS
        assert conversation.is_shared is False
        assert conversation.description_html == "<p></p>"

    @pytest.mark.django_db
    def test_conversation_share_token_uniqueness(self, workspace, create_user):
        """Test that share tokens are unique."""
        conv1 = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Conversation 1",
        )
        conv2 = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Conversation 2",
        )

        assert conv1.share_token != conv2.share_token

    @pytest.mark.django_db
    def test_regenerate_share_token(self, workspace, create_user):
        """Test regenerating the share token."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
        )

        old_token = conversation.share_token
        new_token = conversation.regenerate_share_token()

        assert new_token != old_token
        assert conversation.share_token == new_token

    @pytest.mark.django_db
    def test_is_share_valid_when_not_shared(self, workspace, create_user):
        """Test that is_share_valid returns False when not shared."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            is_shared=False,
        )

        assert conversation.is_share_valid() is False

    @pytest.mark.django_db
    def test_is_share_valid_when_shared(self, workspace, create_user):
        """Test that is_share_valid returns True when shared and not expired."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            is_shared=True,
        )

        assert conversation.is_share_valid() is True

    @pytest.mark.django_db
    def test_is_share_valid_when_expired(self, workspace, create_user):
        """Test that is_share_valid returns False when expired."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            is_shared=True,
            share_expires_at=timezone.now() - timedelta(hours=1),
        )

        assert conversation.is_share_valid() is False


@pytest.mark.unit
class TestConversationVersionModel:
    """Tests for the ConversationVersion model."""

    @pytest.mark.django_db
    def test_version_creation(self, workspace, create_user):
        """Test creating a conversation version."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Test Conversation",
            description_html="<p>Test content</p>",
        )

        version = ConversationVersion.objects.create(
            workspace=workspace,
            conversation=conversation,
            owned_by=create_user,
            name="Test Conversation",
            description_html="<p>Test content</p>",
        )

        assert version.id is not None
        assert version.version_number == 1
        assert version.conversation == conversation
        assert version.name == "Test Conversation"

    @pytest.mark.django_db
    def test_version_auto_increment(self, workspace, create_user):
        """Test that version numbers auto-increment."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
        )

        v1 = ConversationVersion.objects.create(
            workspace=workspace,
            conversation=conversation,
            owned_by=create_user,
            version_number=1,
        )
        v2 = ConversationVersion.objects.create(
            workspace=workspace,
            conversation=conversation,
            owned_by=create_user,
        )

        assert v1.version_number == 1
        assert v2.version_number == 2

    @pytest.mark.django_db
    def test_create_version_helper(self, workspace, create_user):
        """Test the create_version class method."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Test Conversation",
            description_html="<p>Content</p>",
            metadata={"key": "value"},
        )

        version = ConversationVersion.create_version(
            conversation=conversation,
            user=create_user,
            label="v1.0",
            change_summary="Initial version",
        )

        assert version.name == "Test Conversation"
        assert version.description_html == "<p>Content</p>"
        assert version.metadata == {"key": "value"}
        assert version.label == "v1.0"
        assert version.change_summary == "Initial version"


@pytest.mark.unit
class TestConversationShareModel:
    """Tests for the ConversationShare model."""

    @pytest.mark.django_db
    def test_share_creation_with_user(self, workspace, create_user):
        """Test creating a share with a user."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
        )

        # Create another user to share with
        from plane.db.models import User
        shared_user = User.objects.create(
            email="shared@test.com",
            username="shareduser",
        )

        share = ConversationShare.objects.create(
            conversation=conversation,
            shared_with=shared_user,
            permission=ConversationShare.VIEWER,
        )

        assert share.id is not None
        assert share.conversation == conversation
        assert share.shared_with == shared_user
        assert share.permission == ConversationShare.VIEWER
        assert share.accepted is False

    @pytest.mark.django_db
    def test_share_creation_with_email(self, workspace, create_user):
        """Test creating a share with an email."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
        )

        share = ConversationShare.objects.create(
            conversation=conversation,
            email="invited@test.com",
            permission=ConversationShare.EDITOR,
        )

        assert share.email == "invited@test.com"
        assert share.shared_with is None
        assert share.permission == ConversationShare.EDITOR

    @pytest.mark.django_db
    def test_share_is_valid(self, workspace, create_user):
        """Test the is_valid method."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
        )

        # Valid share (no expiry)
        share1 = ConversationShare.objects.create(
            conversation=conversation,
            email="test1@test.com",
        )
        assert share1.is_valid() is True

        # Expired share
        share2 = ConversationShare.objects.create(
            conversation=conversation,
            email="test2@test.com",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        assert share2.is_valid() is False
