import pytest
from django.urls import reverse
from rest_framework import status

from plane.db.models import Conversation, ConversationVersion


@pytest.mark.unit
class TestConversationEndpoint:
    """Tests for the Conversation API endpoint."""

    @pytest.mark.django_db
    def test_list_conversations(self, session_client, workspace, create_user):
        """Test listing conversations."""
        # Create some conversations
        Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Conversation 1",
            access=Conversation.PUBLIC_ACCESS,
        )
        Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Conversation 2",
            access=Conversation.PRIVATE_ACCESS,
        )

        response = session_client.get(
            f"/api/v1/workspaces/{workspace.slug}/conversations/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 2

    @pytest.mark.django_db
    def test_create_conversation(self, session_client, workspace, create_user):
        """Test creating a conversation."""
        response = session_client.post(
            f"/api/v1/workspaces/{workspace.slug}/conversations/",
            data={
                "name": "New Conversation",
                "description_html": "<p>Test content</p>",
                "access": Conversation.PRIVATE_ACCESS,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "New Conversation"
        assert data["access"] == Conversation.PRIVATE_ACCESS

    @pytest.mark.django_db
    def test_get_conversation_detail(self, session_client, workspace, create_user):
        """Test getting a conversation detail."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Test Conversation",
            description_html="<p>Content</p>",
        )

        response = session_client.get(
            f"/api/v1/workspaces/{workspace.slug}/conversations/{conversation.id}/"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Test Conversation"
        assert data["description_html"] == "<p>Content</p>"

    @pytest.mark.django_db
    def test_update_conversation(self, session_client, workspace, create_user):
        """Test updating a conversation."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Original Name",
        )

        response = session_client.patch(
            f"/api/v1/workspaces/{workspace.slug}/conversations/{conversation.id}/",
            data={"name": "Updated Name"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == "Updated Name"

    @pytest.mark.django_db
    def test_delete_conversation(self, session_client, workspace, create_user):
        """Test deleting a conversation."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="To Delete",
        )

        response = session_client.delete(
            f"/api/v1/workspaces/{workspace.slug}/conversations/{conversation.id}/"
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Conversation.objects.filter(id=conversation.id).exists()


@pytest.mark.unit
class TestConversationVersionEndpoint:
    """Tests for the ConversationVersion API endpoint."""

    @pytest.mark.django_db
    def test_list_versions(self, session_client, workspace, create_user):
        """Test listing conversation versions."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Test Conversation",
        )

        # Create some versions
        ConversationVersion.objects.create(
            workspace=workspace,
            conversation=conversation,
            owned_by=create_user,
            version_number=1,
        )
        ConversationVersion.objects.create(
            workspace=workspace,
            conversation=conversation,
            owned_by=create_user,
            version_number=2,
        )

        response = session_client.get(
            f"/api/v1/workspaces/{workspace.slug}/conversations/{conversation.id}/versions/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 2

    @pytest.mark.django_db
    def test_create_version(self, session_client, workspace, create_user):
        """Test creating a conversation version."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Test Conversation",
            description_html="<p>Current content</p>",
        )

        response = session_client.post(
            f"/api/v1/workspaces/{workspace.slug}/conversations/{conversation.id}/versions/",
            data={
                "label": "v1.0",
                "change_summary": "Initial version",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["label"] == "v1.0"
        assert data["change_summary"] == "Initial version"
        assert data["description_html"] == "<p>Current content</p>"

    @pytest.mark.django_db
    def test_get_version_detail(self, session_client, workspace, create_user):
        """Test getting a version detail."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
        )

        version = ConversationVersion.objects.create(
            workspace=workspace,
            conversation=conversation,
            owned_by=create_user,
            version_number=1,
            description_html="<p>Version 1 content</p>",
        )

        response = session_client.get(
            f"/api/v1/workspaces/{workspace.slug}/conversations/{conversation.id}/versions/{version.id}/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["description_html"] == "<p>Version 1 content</p>"


@pytest.mark.unit
class TestConversationShareTokenEndpoint:
    """Tests for the ConversationShareToken API endpoint."""

    @pytest.mark.django_db
    def test_enable_sharing(self, session_client, workspace, create_user):
        """Test enabling sharing for a conversation."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            is_shared=False,
        )

        response = session_client.post(
            f"/api/v1/workspaces/{workspace.slug}/conversations/{conversation.id}/share-token/"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_shared"] is True
        assert data["share_token"] is not None

    @pytest.mark.django_db
    def test_disable_sharing(self, session_client, workspace, create_user):
        """Test disabling sharing for a conversation."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            is_shared=True,
        )

        response = session_client.delete(
            f"/api/v1/workspaces/{workspace.slug}/conversations/{conversation.id}/share-token/"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_shared"] is False

    @pytest.mark.django_db
    def test_regenerate_share_token(self, session_client, workspace, create_user):
        """Test regenerating the share token."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            is_shared=True,
        )
        old_token = conversation.share_token

        response = session_client.patch(
            f"/api/v1/workspaces/{workspace.slug}/conversations/{conversation.id}/share-token/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["share_token"] != old_token


@pytest.mark.unit
class TestPublicConversationEndpoint:
    """Tests for the public conversation access endpoint."""

    @pytest.mark.django_db
    def test_access_shared_conversation(self, api_client, workspace, create_user):
        """Test accessing a shared conversation via share token."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            name="Shared Conversation",
            description_html="<p>Public content</p>",
            is_shared=True,
        )

        # No authentication required
        response = api_client.get(
            f"/api/v1/public/conversations/{conversation.share_token}/"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Shared Conversation"

    @pytest.mark.django_db
    def test_access_non_shared_conversation(self, api_client, workspace, create_user):
        """Test that non-shared conversations cannot be accessed."""
        conversation = Conversation.objects.create(
            workspace=workspace,
            owned_by=create_user,
            is_shared=False,
        )

        response = api_client.get(
            f"/api/v1/public/conversations/{conversation.share_token}/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_access_invalid_share_token(self, api_client):
        """Test accessing with an invalid share token."""
        response = api_client.get(
            "/api/v1/public/conversations/invalid-token-12345/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
