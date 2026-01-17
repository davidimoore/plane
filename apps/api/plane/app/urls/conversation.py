from django.urls import path

from plane.app.views import (
    ConversationEndpoint,
    ConversationVersionEndpoint,
    ConversationShareEndpoint,
    PublicConversationEndpoint,
    ConversationShareTokenEndpoint,
)


urlpatterns = [
    # Conversation CRUD
    path(
        "workspaces/<str:slug>/conversations/",
        ConversationEndpoint.as_view(),
        name="workspace-conversations",
    ),
    path(
        "workspaces/<str:slug>/conversations/<uuid:pk>/",
        ConversationEndpoint.as_view(),
        name="workspace-conversation-detail",
    ),
    # Conversation Versions
    path(
        "workspaces/<str:slug>/conversations/<uuid:conversation_id>/versions/",
        ConversationVersionEndpoint.as_view(),
        name="conversation-versions",
    ),
    path(
        "workspaces/<str:slug>/conversations/<uuid:conversation_id>/versions/<uuid:pk>/",
        ConversationVersionEndpoint.as_view(),
        name="conversation-version-detail",
    ),
    # Conversation Shares (with specific users)
    path(
        "workspaces/<str:slug>/conversations/<uuid:conversation_id>/shares/",
        ConversationShareEndpoint.as_view(),
        name="conversation-shares",
    ),
    path(
        "workspaces/<str:slug>/conversations/<uuid:conversation_id>/shares/<uuid:pk>/",
        ConversationShareEndpoint.as_view(),
        name="conversation-share-detail",
    ),
    # Conversation Share Token (public sharing)
    path(
        "workspaces/<str:slug>/conversations/<uuid:conversation_id>/share-token/",
        ConversationShareTokenEndpoint.as_view(),
        name="conversation-share-token",
    ),
    # Public access (no authentication required)
    path(
        "public/conversations/<str:share_token>/",
        PublicConversationEndpoint.as_view(),
        name="public-conversation",
    ),
    path(
        "public/conversations/<str:share_token>/versions/",
        PublicConversationEndpoint.as_view(),
        name="public-conversation-versions",
    ),
    path(
        "public/conversations/<str:share_token>/versions/<uuid:version_id>/",
        PublicConversationEndpoint.as_view(),
        name="public-conversation-version-detail",
    ),
]
