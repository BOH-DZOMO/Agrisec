from decimal import Decimal
import re

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from agrisec.farms.models import Farm
from agrisec.farms.models import SensorDevice
from agrisec.farms.models import TelemetryReading

MAC_ADDRESS_REGEX = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def normalize_mac_address(value: str) -> str:
    cleaned = value.strip()
    if not MAC_ADDRESS_REGEX.match(cleaned):
        msg = "Enter a valid MAC address (e.g., AA:BB:CC:DD:EE:FF)."
        raise serializers.ValidationError(msg)
    return cleaned.replace("-", ":").upper()


def validate_environmental_metrics(
    temperature: Decimal | None,
    soil_moisture: Decimal | None,
) -> None:
    if temperature is None and soil_moisture is None:
        raise serializers.ValidationError(
            "Provide at least one metric: 'temperature' or 'soil_moisture'.",
        )
    if soil_moisture is not None and not (Decimal(0) <= soil_moisture <= Decimal(100)):
        raise serializers.ValidationError(
            {"soil_moisture": "Soil moisture must be between 0 and 100."},
        )


class TelemetrySummaryInlineSerializer(serializers.ModelSerializer):
    """Compact read-only representation of a single telemetry reading."""

    class Meta:
        model = TelemetryReading
        fields = ["id", "temperature", "soil_moisture", "timestamp"]
        read_only_fields = fields


class TelemetryReadingSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source="device.name", read_only=True)

    class Meta:
        model = TelemetryReading
        fields = [
            "id",
            "device",
            "device_name",
            "temperature",
            "soil_moisture",
            "timestamp",
        ]
        read_only_fields = ["id", "device_name", "timestamp"]

    def validate_device(self, device: SensorDevice) -> SensorDevice:
        request = self.context.get("request")
        if request and request.user.is_authenticated and device.farm.owner_id != request.user.id:
            msg = "You do not have permission to log readings for this device."
            raise serializers.ValidationError(msg)
        return device

    def validate(self, attrs):
        validate_environmental_metrics(
            attrs.get("temperature"),
            attrs.get("soil_moisture"),
        )
        return attrs


class DeviceTelemetryIngestSerializer(serializers.Serializer):
    """Payload sent directly by IoT microcontrollers (ESP32, STM32, Arduino)."""

    mac_address = serializers.CharField(
        max_length=17,
        help_text="Registered MAC address of the active sensor device (e.g., AA:BB:CC:DD:EE:FF).",
    )
    temperature = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Ambient or soil temperature in Celsius.",
    )
    soil_moisture = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Soil moisture percentage (0.00 to 100.00).",
    )

    def validate_mac_address(self, value: str) -> str:
        return normalize_mac_address(value)

    def validate(self, attrs):
        validate_environmental_metrics(
            attrs.get("temperature"),
            attrs.get("soil_moisture"),
        )
        mac_address = attrs["mac_address"]
        try:
            device = SensorDevice.objects.get(mac_address__iexact=mac_address)
        except SensorDevice.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"mac_address": "No registered sensor device matches this MAC address."},
            ) from exc

        if not device.is_active:
            raise serializers.ValidationError(
                {"mac_address": "This sensor device is currently inactive."},
            )

        attrs["device"] = device
        return attrs

    def create(self, validated_data) -> TelemetryReading:
        return TelemetryReading.objects.create(
            device=validated_data["device"],
            temperature=validated_data.get("temperature"),
            soil_moisture=validated_data.get("soil_moisture"),
        )


class SensorDeviceSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source="farm.name", read_only=True)
    latest_reading = serializers.SerializerMethodField()

    class Meta:
        model = SensorDevice
        fields = [
            "id",
            "farm",
            "farm_name",
            "name",
            "mac_address",
            "device_type",
            "is_active",
            "latest_reading",
            "created_at",
        ]
        read_only_fields = ["id", "farm_name", "latest_reading", "created_at"]

    def validate_mac_address(self, value: str) -> str:
        normalized = normalize_mac_address(value)
        qs = SensorDevice.objects.filter(mac_address__iexact=normalized)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            msg = "A sensor device with this MAC address already exists."
            raise serializers.ValidationError(msg)
        return normalized

    def validate_farm(self, farm: Farm) -> Farm:
        request = self.context.get("request")
        if request and request.user.is_authenticated and farm.owner_id != request.user.id:
            msg = "You can only register devices to your own farms."
            raise serializers.ValidationError(msg)
        return farm

    @extend_schema_field(TelemetrySummaryInlineSerializer(allow_null=True))
    def get_latest_reading(self, obj: SensorDevice):
        prefetched = getattr(obj, "prefetched_readings", None)
        reading = prefetched[0] if prefetched is not None and len(prefetched) > 0 else (
            None if prefetched is not None else obj.readings.first()
        )
        if reading is None:
            return None
        return TelemetrySummaryInlineSerializer(reading).data


class FarmSerializer(serializers.ModelSerializer):
    device_count = serializers.IntegerField(read_only=True, default=0)
    active_device_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Farm
        fields = [
            "id",
            "name",
            "location",
            "device_count",
            "active_device_count",
            "created_at",
        ]
        read_only_fields = ["id", "device_count", "active_device_count", "created_at"]


class FarmSummarySerializer(serializers.Serializer):
    """Aggregated device & environmental statistics for a single farm."""

    farm_id = serializers.UUIDField()
    farm_name = serializers.CharField()
    total_devices = serializers.IntegerField()
    active_devices = serializers.IntegerField()
    total_readings = serializers.IntegerField()
    avg_temperature = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    min_temperature = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    max_temperature = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    avg_soil_moisture = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    min_soil_moisture = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    max_soil_moisture = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    latest_reading_at = serializers.DateTimeField(allow_null=True)
