from django.contrib.auth.backends import ModelBackend
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model

class AsyncSafeBackend(ModelBackend):
    async def aget_user(self, user_id):
        UserModel = get_user_model()
        try:
            user = await sync_to_async(UserModel.objects.get, thread_sensitive=True)(pk=user_id)
            if self.user_can_authenticate(user):
                return user
        except UserModel.DoesNotExist:
            return None