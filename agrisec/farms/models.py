from django.db import models
from django.conf import settings 
import uuid
from agrisec.global_utils.models import DeviceType

class Farm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='farms')
    name = models.CharField(max_length=255, help_text="e.g., Greenhouse Alpha")
    location = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.owner.username}"

class SensorDevice(models.Model):
  
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='devices')
    name = models.CharField(max_length=100, help_text="e.g., North Field Soil Sensor")
    mac_address = models.CharField(max_length=17, unique=True, help_text="Used for device authentication")
    device_type = models.CharField(max_length=20, choices=DeviceType, default='ESP32')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.mac_address})"

class TelemetryReading(models.Model):
    id = models.BigAutoField(primary_key=True)
    device = models.ForeignKey(SensorDevice, on_delete=models.CASCADE, related_name='readings')
    
    # Environmental Data
    temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Celsius")
    soil_moisture = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Percentage (0-100)")
    
    # Auto-recorded time
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Crucial for telemetry data: order by newest first and index the timestamp
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['device', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.device.name} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
