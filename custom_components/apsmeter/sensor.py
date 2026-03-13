# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# ... (keep your full copyright header)

import logging
import itertools
import statistics
from datetime import datetime, timedelta

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.util import dt as dtutil
from homeassistant.helpers import entity_platform

from homeassistant_historical_sensor import (
    HistoricalSensor,
    HistoricalState,
    PollUpdateMixin,
)

from .api import API
from .const import DOMAIN, NAME, CONF_USERNAME, CONF_PASSWORD

PLATFORM = "sensor"
_LOGGER = logging.getLogger(__name__)
SERVICE_COMMAND = "get_aps_data"


class Sensor(PollUpdateMixin, HistoricalSensor, SensorEntity):
    """APS Meter Historical Sensor."""

    def __init__(self, api: API, attr_name: str, attr_unique_id: str, attr_entity_id: str):
        super().__init__()

        _LOGGER.info("Sensor __init__ called %s", attr_name)

        self.api = api  # ? Shared API instance with credentials

        self.UPDATE_INTERVAL = timedelta(days=30)
        self._attr_has_entity_name = True
        self._attr_name = attr_name
        self._attr_unique_id = attr_unique_id
        self._attr_entity_id = attr_entity_id
        self._attr_entity_registry_enabled_default = True
        self._attr_state = None
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

    async def async_update_historical(self):
        """Fetch historical data and convert to HistoricalState objects."""
        data = await self.api.fetch(
            self._attr_name,
            start=datetime.now() - timedelta(days=1),
            step=timedelta(minutes=60),
        )

        hist_states = [
            HistoricalState(
                state=state,
                timestamp=dt.timestamp(),   # HistoricalSensor expects unix timestamp
            )
            for (dt, state) in data
        ]
        self._attr_historical_states = hist_states

    @property
    def statistic_id(self) -> str:
        return self.entity_id

    def get_statistic_metadata(self) -> StatisticMetaData:
        meta = super().get_statistic_metadata()
        meta["has_sum"] = True
        meta["has_mean"] = True
        return meta

    async def async_calculate_statistic_data(
        self, hist_states: list[HistoricalState], *, latest: dict | None = None
    ) -> list[StatisticData]:
        accumulated = latest["sum"] if latest else 0
        ret = []

        for dt, collection_it in itertools.groupby(
            hist_states, key=self._hour_block_for_hist_state
        ):
            collection = list(collection_it)
            mean = statistics.mean([x.state for x in collection])
            partial_sum = sum([x.state for x in collection])
            accumulated += partial_sum

            ret.append(
                StatisticData(
                    start=dtutil.as_local(dt),
                    state=partial_sum,
                    mean=mean,
                    sum=accumulated,
                )
            )
        return ret

    def _hour_block_for_hist_state(self, hist_state: HistoricalState) -> datetime:
        """Group by hour (APS already adjusted in API)."""
        dt = datetime.fromtimestamp(hist_state.timestamp)
        if dt.minute == 0 and dt.second == 0:
            dt = dt - timedelta(hours=1)
        return dt.replace(minute=0, second=0, microsecond=0)

    async def async_get_aps_data(self, **kwargs) -> None:
        """Service call to refresh data."""
        _LOGGER.info("get_aps_data called with %s", kwargs)
        await self._async_historical_handle_update()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Set up APS Meter sensors from config entry."""
    _LOGGER.info("async_setup_entry called")

    # Get credentials from config flow
    username = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]

    # Create ONE shared API instance with credentials
    api = API(username=username, password=password)

    # Store it so other platforms can use it later if needed
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = api

    # Create the four sensors, passing the shared api
    sensors = [
        Sensor(
            api=api,
            attr_name="aps_total_usage",
            attr_unique_id="aps_total_usage",
            attr_entity_id="aps_total_usage",
        ),
        Sensor(
            api=api,
            attr_name="aps_onpeak_usage",
            attr_unique_id="aps_onpeak_usage",
            attr_entity_id="aps_onpeak_usage",
        ),
        Sensor(
            api=api,
            attr_name="aps_offpeak_usage",
            attr_unique_id="aps_offpeak_usage",
            attr_entity_id="aps_offpeak_usage",
        ),
        Sensor(
            api=api,
            attr_name="aps_otherpeak_usage",
            attr_unique_id="aps_otherpeak_usage",
            attr_entity_id="aps_otherpeak_usage",
        ),
    ]

    async_add_devices(sensors)

    # Register the service
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(SERVICE_COMMAND, None, "async_get_aps_data")
    
    
