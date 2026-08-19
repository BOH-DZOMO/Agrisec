from django.db import models 
from django.utils.translation import gettext_lazy as _



class DeviceType(models.TextChoices):
    ESP32 = 'ESP32', _('ESP32')
    STM32 = 'STM32', _('STM32')
    ARDUINO = 'ARDUINO', _('Arduino')
    OTHER = 'OTHER', _('Other')
