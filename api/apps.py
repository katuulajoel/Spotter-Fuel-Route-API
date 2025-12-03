from django.apps import AppConfig
from django.conf import settings
import threading


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        from .preload import preload_station_coords

        if settings.PRELOAD_STATIONS_ON_START and settings.PRELOAD_STATION_LIMIT > 0:
            # Run in a background thread so startup isn't blocked.
            threading.Thread(
                target=preload_station_coords,
                args=(settings.PRELOAD_STATION_LIMIT,),
                daemon=True,
            ).start()
