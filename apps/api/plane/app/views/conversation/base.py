# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Django imports
from django.db.models import Count

# Module imports
from plane.db.models import Conversation, Workspace
from plane.app.views.base import BaseAPIView
from plane.app.serializers import (
    ConversationSerializer,
    ConversationDetailSerializer,
    ConversationCreateSerializer,
    ConversationUpdateSerializer,
)
from plane.app.permissions import WorkSpaceBasePermission


class ConversationEndpoint(BaseAPIView):
    """
    Endpoint for managing conversations within a workspace.
    Supports CRUD operations for conversations.
    """

    permission_classes = [WorkSpaceBasePermission]

    def get_queryset(self):
        """Get conversations for the current workspace."""
        return (
            Conversation.objects.filter(
                workspace__slug=self.kwargs.get("slug"),
                archived_at__isnull=True,
            )
            .select_related("owned_by", "workspace")
            .annotate(version_count=Count("versions"))
            .order_by("-created_at")
        )

    def get(self, request, slug, pk=None):
        """
        Get a single conversation or list all conversations.

        - GET /workspaces/<slug>/conversations/ - List all conversations
        - GET /workspaces/<slug>/conversations/<pk>/ - Get a single conversation
        """
        if pk:
            # Return a single conversation with details
            try:
                conversation = self.get_queryset().get(pk=pk)
            except Conversation.DoesNotExist:
                return Response(
                    {"error": "Conversation not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Check if user has access
            if (
                conversation.access == Conversation.PRIVATE_ACCESS
                and conversation.owned_by != request.user
            ):
                return Response(
                    {"error": "You do not have permission to view this conversation"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = ConversationDetailSerializer(conversation)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # List all conversations the user can access
        queryset = self.get_queryset()

        # Filter: show public conversations and user's own private conversations
        queryset = queryset.filter(
            access=Conversation.PUBLIC_ACCESS
        ) | queryset.filter(
            owned_by=request.user
        )

        # Apply optional filters
        if request.query_params.get("owned_by_me"):
            queryset = queryset.filter(owned_by=request.user)

        if request.query_params.get("shared"):
            queryset = queryset.filter(is_shared=True)

        serializer = ConversationSerializer(queryset.distinct(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, slug):
        """
        Create a new conversation.

        POST /workspaces/<slug>/conversations/
        """
        try:
            workspace = Workspace.objects.get(slug=slug)
        except Workspace.DoesNotExist:
            return Response(
                {"error": "Workspace not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ConversationCreateSerializer(
            data=request.data,
            context={
                "workspace_id": workspace.id,
                "owned_by_id": request.user.id,
            },
        )

        if serializer.is_valid():
            conversation = serializer.save(
                created_by=request.user,
                updated_by=request.user,
            )
            # Return the created conversation with full details
            response_serializer = ConversationDetailSerializer(conversation)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, slug, pk):
        """
        Update a conversation.

        PATCH /workspaces/<slug>/conversations/<pk>/
        """
        try:
            conversation = Conversation.objects.get(
                workspace__slug=slug,
                pk=pk,
            )
        except Conversation.DoesNotExist:
            return Response(
                {"error": "Conversation not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user is the owner
        if conversation.owned_by != request.user:
            return Response(
                {"error": "You do not have permission to update this conversation"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ConversationUpdateSerializer(
            conversation,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            conversation = serializer.save(updated_by=request.user)
            response_serializer = ConversationDetailSerializer(conversation)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug, pk):
        """
        Delete a conversation.

        DELETE /workspaces/<slug>/conversations/<pk>/
        """
        try:
            conversation = Conversation.objects.get(
                workspace__slug=slug,
                pk=pk,
            )
        except Conversation.DoesNotExist:
            return Response(
                {"error": "Conversation not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user is the owner
        if conversation.owned_by != request.user:
            return Response(
                {"error": "You do not have permission to delete this conversation"},
                status=status.HTTP_403_FORBIDDEN,
            )

        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
