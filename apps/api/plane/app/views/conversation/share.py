# Third party imports
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

# Django imports
from django.utils import timezone

# Module imports
from plane.db.models import Conversation, ConversationShare, ConversationVersion
from plane.app.views.base import BaseAPIView
from plane.app.serializers import (
    ConversationShareSerializer,
    ConversationShareCreateSerializer,
    PublicConversationSerializer,
    PublicConversationVersionSerializer,
)
from plane.app.permissions import WorkSpaceBasePermission


class ConversationShareEndpoint(BaseAPIView):
    """
    Endpoint for managing conversation shares.
    Allows sharing conversations with specific users or via email invitation.
    """

    permission_classes = [WorkSpaceBasePermission]

    def get_conversation(self, slug, conversation_id, user):
        """Get the conversation and check ownership."""
        try:
            conversation = Conversation.objects.get(
                workspace__slug=slug,
                pk=conversation_id,
            )
        except Conversation.DoesNotExist:
            return None, Response(
                {"error": "Conversation not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Only the owner can manage shares
        if conversation.owned_by != user:
            return None, Response(
                {"error": "You do not have permission to manage shares for this conversation"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return conversation, None

    def get(self, request, slug, conversation_id):
        """
        List all shares for a conversation.

        GET /workspaces/<slug>/conversations/<conversation_id>/shares/
        """
        conversation, error = self.get_conversation(slug, conversation_id, request.user)
        if error:
            return error

        shares = (
            ConversationShare.objects.filter(conversation=conversation)
            .select_related("shared_with")
            .order_by("-created_at")
        )

        serializer = ConversationShareSerializer(shares, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, slug, conversation_id):
        """
        Create a new share for a conversation.

        POST /workspaces/<slug>/conversations/<conversation_id>/shares/
        """
        conversation, error = self.get_conversation(slug, conversation_id, request.user)
        if error:
            return error

        serializer = ConversationShareCreateSerializer(
            data=request.data,
            context={"conversation": conversation},
        )

        if serializer.is_valid():
            share = serializer.save(
                created_by=request.user,
                updated_by=request.user,
            )
            response_serializer = ConversationShareSerializer(share)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug, conversation_id, pk):
        """
        Revoke a share.

        DELETE /workspaces/<slug>/conversations/<conversation_id>/shares/<pk>/
        """
        conversation, error = self.get_conversation(slug, conversation_id, request.user)
        if error:
            return error

        try:
            share = ConversationShare.objects.get(
                conversation=conversation,
                pk=pk,
            )
        except ConversationShare.DoesNotExist:
            return Response(
                {"error": "Share not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        share.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicConversationEndpoint(BaseAPIView):
    """
    Public endpoint for accessing shared conversations via share token.
    No authentication required.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, share_token, version_id=None):
        """
        Access a shared conversation via share token.

        - GET /public/conversations/<share_token>/
          Get the conversation
        - GET /public/conversations/<share_token>/versions/
          List all versions
        - GET /public/conversations/<share_token>/versions/<version_id>/
          Get a specific version
        """
        try:
            conversation = Conversation.objects.get(
                share_token=share_token,
                is_shared=True,
            )
        except Conversation.DoesNotExist:
            return Response(
                {"error": "Conversation not found or not shared"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if share is still valid
        if not conversation.is_share_valid():
            return Response(
                {"error": "Share link has expired"},
                status=status.HTTP_410_GONE,
            )

        # Handle version requests
        if version_id:
            try:
                version = ConversationVersion.objects.get(
                    conversation=conversation,
                    pk=version_id,
                )
            except ConversationVersion.DoesNotExist:
                return Response(
                    {"error": "Version not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            serializer = PublicConversationVersionSerializer(version)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # Check if listing versions was requested
        if request.path.endswith("/versions/"):
            versions = (
                ConversationVersion.objects.filter(conversation=conversation)
                .order_by("-version_number")
            )
            serializer = PublicConversationVersionSerializer(versions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # Return the conversation
        serializer = PublicConversationSerializer(conversation)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ConversationShareTokenEndpoint(BaseAPIView):
    """
    Endpoint for managing the conversation share token.
    Allows enabling/disabling sharing and regenerating the share token.
    """

    permission_classes = [WorkSpaceBasePermission]

    def get_conversation(self, slug, conversation_id, user):
        """Get the conversation and check ownership."""
        try:
            conversation = Conversation.objects.get(
                workspace__slug=slug,
                pk=conversation_id,
            )
        except Conversation.DoesNotExist:
            return None, Response(
                {"error": "Conversation not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if conversation.owned_by != user:
            return None, Response(
                {"error": "You do not have permission to manage this conversation"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return conversation, None

    def get(self, request, slug, conversation_id):
        """
        Get the current share status and token.

        GET /workspaces/<slug>/conversations/<conversation_id>/share-token/
        """
        conversation, error = self.get_conversation(slug, conversation_id, request.user)
        if error:
            return error

        return Response({
            "is_shared": conversation.is_shared,
            "share_token": conversation.share_token if conversation.is_shared else None,
            "share_expires_at": conversation.share_expires_at,
            "share_url": f"/public/conversations/{conversation.share_token}/" if conversation.is_shared else None,
        }, status=status.HTTP_200_OK)

    def post(self, request, slug, conversation_id):
        """
        Enable sharing and optionally set expiry.

        POST /workspaces/<slug>/conversations/<conversation_id>/share-token/
        """
        conversation, error = self.get_conversation(slug, conversation_id, request.user)
        if error:
            return error

        conversation.is_shared = True

        # Set expiry if provided
        if "expires_at" in request.data:
            conversation.share_expires_at = request.data.get("expires_at")

        conversation.save(update_fields=["is_shared", "share_expires_at", "updated_at"])

        return Response({
            "is_shared": conversation.is_shared,
            "share_token": conversation.share_token,
            "share_expires_at": conversation.share_expires_at,
            "share_url": f"/public/conversations/{conversation.share_token}/",
        }, status=status.HTTP_200_OK)

    def patch(self, request, slug, conversation_id):
        """
        Regenerate the share token.

        PATCH /workspaces/<slug>/conversations/<conversation_id>/share-token/
        """
        conversation, error = self.get_conversation(slug, conversation_id, request.user)
        if error:
            return error

        new_token = conversation.regenerate_share_token()

        return Response({
            "is_shared": conversation.is_shared,
            "share_token": new_token,
            "share_expires_at": conversation.share_expires_at,
            "share_url": f"/public/conversations/{new_token}/" if conversation.is_shared else None,
        }, status=status.HTTP_200_OK)

    def delete(self, request, slug, conversation_id):
        """
        Disable sharing.

        DELETE /workspaces/<slug>/conversations/<conversation_id>/share-token/
        """
        conversation, error = self.get_conversation(slug, conversation_id, request.user)
        if error:
            return error

        conversation.is_shared = False
        conversation.share_expires_at = None
        conversation.save(update_fields=["is_shared", "share_expires_at", "updated_at"])

        return Response({
            "is_shared": False,
            "share_token": None,
            "share_expires_at": None,
            "share_url": None,
        }, status=status.HTTP_200_OK)
