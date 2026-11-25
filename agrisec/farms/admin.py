from django.contrib import admin

from agrisec.farms.models import Farm
from agrisec.farms.models import SensorDevice
from agrisec.farms.models import TelemetryReading


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "location", "created_at")
    search_fields = ("name", "location", "owner__email", "owner__username")
    list_filter = ("created_at",)
    readonly_fields = ("id", "created_at")


@admin.register(SensorDevice)
class SensorDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "mac_address", "device_type", "farm", "is_active", "created_at")
    search_fields = ("name", "mac_address", "farm__name")
    list_filter = ("device_type", "is_active", "created_at")
    readonly_fields = ("id", "created_at")


@admin.register(TelemetryReading)
class TelemetryReadingAdmin(admin.ModelAdmin):
    list_display = ("device", "temperature", "soil_moisture", "timestamp")
    search_fields = ("device__name", "device__mac_address")
    list_filter = ("timestamp", "device__device_type")
    readonly_fields = ("id", "timestamp")
