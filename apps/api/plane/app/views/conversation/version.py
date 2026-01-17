# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.db.models import Conversation, ConversationVersion
from plane.app.views.base import BaseAPIView
from plane.app.serializers import (
    ConversationVersionSerializer,
    ConversationVersionDetailSerializer,
    ConversationVersionCreateSerializer,
)
from plane.app.permissions import WorkSpaceBasePermission


class ConversationVersionEndpoint(BaseAPIView):
    """
    Endpoint for managing conversation versions.
    Supports listing versions, getting a specific version, and creating new versions.
    """

    permission_classes = [WorkSpaceBasePermission]

    def get_conversation(self, slug, conversation_id, user):
        """Get the conversation and check access permissions."""
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

        # Check if user has access
        if (
            conversation.access == Conversation.PRIVATE_ACCESS
            and conversation.owned_by != user
        ):
            return None, Response(
                {"error": "You do not have permission to access this conversation"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return conversation, None

    def get(self, request, slug, conversation_id, pk=None):
        """
        Get conversation versions.

        - GET /workspaces/<slug>/conversations/<conversation_id>/versions/
          List all versions
        - GET /workspaces/<slug>/conversations/<conversation_id>/versions/<pk>/
          Get a specific version
        """
        conversation, error = self.get_conversation(slug, conversation_id, request.user)
        if error:
            return error

        if pk:
            # Return a single version with full details
            try:
                version = ConversationVersion.objects.get(
                    conversation=conversation,
                    pk=pk,
                )
            except ConversationVersion.DoesNotExist:
                return Response(
                    {"error": "Version not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            serializer = ConversationVersionDetailSerializer(version)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # List all versions
        versions = (
            ConversationVersion.objects.filter(conversation=conversation)
            .select_related("owned_by")
            .order_by("-version_number")
        )

        serializer = ConversationVersionSerializer(versions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, slug, conversation_id):
        """
        Create a new version of the conversation.

        POST /workspaces/<slug>/conversations/<conversation_id>/versions/

        This creates a snapshot of the current conversation state.
        """
        conversation, error = self.get_conversation(slug, conversation_id, request.user)
        if error:
            return error

        # Only the owner can create versions
        if conversation.owned_by != request.user:
            return Response(
                {"error": "You do not have permission to create versions for this conversation"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ConversationVersionCreateSerializer(
            data=request.data,
            context={
                "conversation": conversation,
                "user": request.user,
            },
        )

        if serializer.is_valid():
            version = serializer.save(
                created_by=request.user,
                updated_by=request.user,
            )
            response_serializer = ConversationVersionDetailSerializer(version)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug, conversation_id, pk):
        """
        Delete a conversation version.

        DELETE /workspaces/<slug>/conversations/<conversation_id>/versions/<pk>/
        """
        conversation, error = self.get_conversation(slug, conversation_id, request.user)
        if error:
            return error

        # Only the owner can delete versions
        if conversation.owned_by != request.user:
            return Response(
                {"error": "You do not have permission to delete versions"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            version = ConversationVersion.objects.get(
                conversation=conversation,
                pk=pk,
            )
        except ConversationVersion.DoesNotExist:
            return Response(
                {"error": "Version not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        version.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
