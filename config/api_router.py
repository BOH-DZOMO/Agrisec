from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from agrisec.farms.api.views import FarmViewSet
from agrisec.farms.api.views import SensorDeviceViewSet
from agrisec.farms.api.views import TelemetryReadingViewSet
from agrisec.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("farms", FarmViewSet, basename="farm")
router.register("devices", SensorDeviceViewSet, basename="device")
router.register("readings", TelemetryReadingViewSet, basename="reading")

app_name = "api"
urlpatterns = router.urls
