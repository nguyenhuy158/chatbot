"""Admin panel using SQLAdmin."""
from fastapi import FastAPI, Request
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend

from app.core.config import settings
from app.core.security import decode_token
from app.db.models import Conversation, Feedback, Message, User
from app.db.session import engine


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        # Admin login uses same SSO; this just verifies cookie
        return await self.authenticate(request)

    async def logout(self, request: Request) -> bool:
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.cookies.get("access_token")
        if not token:
            return False
        try:
            payload = decode_token(token)
            return payload.get("role") == "admin"
        except Exception:
            return False


class UserAdmin(ModelView, model=User):
    column_list = [User.email, User.name, User.role, User.reputation_score, User.created_at]
    column_searchable_list = [User.email, User.name]
    column_filters = [User.role, User.tenant_id]


class ConversationAdmin(ModelView, model=Conversation):
    column_list = [Conversation.id, Conversation.title, Conversation.channel, Conversation.created_at]
    column_filters = [Conversation.channel]


class MessageAdmin(ModelView, model=Message):
    column_list = [Message.role, Message.content, Message.model, Message.cost_usd, Message.created_at]
    column_filters = [Message.role, Message.model]
    can_create = False
    can_edit = False


class FeedbackAdmin(ModelView, model=Feedback):
    column_list = [Feedback.rating, Feedback.comment, Feedback.reviewed_action, Feedback.created_at]
    column_filters = [Feedback.rating, Feedback.reviewed_action]
    can_create = False


def setup_admin(app: FastAPI) -> None:
    admin = Admin(
        app,
        engine,
        authentication_backend=AdminAuth(secret_key=settings.APP_SECRET_KEY),
        base_url="/admin",
        title="Chatbot Admin",
    )
    admin.add_view(UserAdmin)
    admin.add_view(ConversationAdmin)
    admin.add_view(MessageAdmin)
    admin.add_view(FeedbackAdmin)
