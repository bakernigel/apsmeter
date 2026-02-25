# Copyright (C) 2021-2023 Luis López <luis@cuarentaydos.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.


#
# This is an example of historical sensor using the
# `homeassistant_historical_sensor module` helper.
#
# Important methods include comments about code itself and reasons behind them
#
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
from .const import DOMAIN, NAME

PLATFORM = "sensor"

_LOGGER = logging.getLogger(__name__)

SERVICE_COMMAND = "get_aps_data"

class Sensor(PollUpdateMixin, HistoricalSensor, SensorEntity):
    #
    # Base clases:
    # - SensorEntity: This is a sensor, obvious
    # - HistoricalSensor: This sensor implements historical sensor methods
    # - PollUpdateMixin: Historical sensors disable poll, this mixing
    #                    reenables poll only for historical states and not for
    #                    present state
    #

    def __init__(self, *args, **kwargs):
    
        _LOGGER.warning(
                  "Sensor __init__ called %s ",
                  kwargs["attr_name"],
        )
        
        super().__init__()

        self.UPDATE_INTERVAL = timedelta(days=30)

        self._attr_has_entity_name = True
        self._attr_name = kwargs["attr_name"]

        self._attr_unique_id = kwargs["attr_unique_id"]
        self._attr_entity_id = kwargs["attr_entity_id"] 

        self._attr_entity_registry_enabled_default = True
        self._attr_state = None

        # Define whatever you are
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY

        # We DON'T opt-in for statistics (don't set state_class). Why?
        #
        # Those statistics are generated from a real sensor, this sensor, but we don't
        # want that hass try to do anything with those statistics because we
        # (HistoricalSensor) handle generation and importing
        #
        # self._attr_state_class = SensorStateClass.MEASUREMENT

        self.api = API()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

    async def async_update_historical(self):
        # Fill `HistoricalSensor._attr_historical_states` with HistoricalState's
        # This functions is equivaled to the `Sensor.async_update` from
        # HomeAssistant core
        #
        # Important: You must provide datetime with tzinfo
        
        hist_states = [
            HistoricalState(
                state=state,
#                timestamp=dtutil.as_local(dt),  # Add tzinfo, required by HistoricalSensor
                 timestamp=dt.timestamp(),            
            )
            for (dt, state) in (await self.api.fetch(self._attr_name,
                start=datetime.now() - timedelta(days=1), step=timedelta(minutes=60))
            )
        ]
        self._attr_historical_states = hist_states

    @property
    def statistic_id(self) -> str:
        return self.entity_id

    def get_statistic_metadata(self) -> StatisticMetaData:
        #
        # Add sum and mean to base statistics metadata
        # Important: HistoricalSensor.get_statistic_metadata returns an
        # internal source by default.
        #
        meta = super().get_statistic_metadata()
        meta["has_sum"] = True
        meta["has_mean"] = True

        return meta

    async def async_calculate_statistic_data(
        self, hist_states: list[HistoricalState], *, latest: dict | None = None
    ) -> list[StatisticData]:
        #
        # Group historical states by hour
        # Calculate sum, mean, etc...
        #

        accumulated = latest["sum"] if latest else 0

        def hour_block_for_hist_state(hist_state: HistoricalState) -> datetime:
            # XX:00:00 states belongs to previous hour block - NOT TRUE FOR APS but api _set_intervalusagedata adds an hour to account for this.
            time_float = hist_state.timestamp
            dt = datetime.fromtimestamp(time_float)
            if dt.minute == 0 and dt.second == 0:
                dt = dt - timedelta(hours=1)
                return dt.replace(minute=0, second=0, microsecond=0)
                
            else:
                return hist_state.dt.replace(minute=0, second=0, microsecond=0)

        ret = []
        for dt, collection_it in itertools.groupby(
            hist_states, key=hour_block_for_hist_state
        ):
            collection = list(collection_it)
            mean = statistics.mean([x.state for x in collection])
            partial_sum = sum([x.state for x in collection])
            accumulated = accumulated + partial_sum

            ret.append(
                StatisticData(
                    start=dtutil.as_local(dt),
                    state=partial_sum,
                    mean=mean,
                    sum=accumulated,
                )
            )

        return ret
        
    async def async_get_aps_data(
        self,
        **kwargs
    ) -> None:        
        """Send a command"""
        _LOGGER.warning(
                  "get_aps_data %s",
                  kwargs,
        )
        await self._async_historical_handle_update()        
  


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,  # noqa DiscoveryInfoType | None
):

    _LOGGER.warning(
                  "async_setup_entry called",
    ) 
         
    device_info = hass.data[DOMAIN][config_entry.entry_id]
# Add  aps_super_offpeak_usage
    sensors = [
        Sensor(config_entry=config_entry, device_info=device_info,attr_name = "aps_total_usage", attr_unique_id = "aps_total_usage", attr_entity_id = "aps_total_usage"),
        Sensor(config_entry=config_entry, device_info=device_info,attr_name = "aps_onpeak_usage", attr_unique_id = "aps_onpeak_usage", attr_entity_id = "aps_onpeak_usage"),
        Sensor(config_entry=config_entry, device_info=device_info,attr_name = "aps_offpeak_usage", attr_unique_id = "aps_offpeak_usage", attr_entity_id = "aps_offpeak_usage"),
        Sensor(config_entry=config_entry, device_info=device_info,attr_name = "aps_otherpeak_usage", attr_unique_id = "aps_otherpeak_usage", attr_entity_id = "aps_otherpeak_usage"),
    ]
    async_add_devices(sensors)
    
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(SERVICE_COMMAND, None, "async_get_aps_data") 
    
    
    
