from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from agrisec.users.api.views import UserViewSet
from agrisec.farms.api.views import FarmViewSet


router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("farms", FarmViewSet)

app_name = "api"
urlpatterns = router.urls
