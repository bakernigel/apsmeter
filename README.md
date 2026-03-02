# APS Meter

Custom Home Assistant integration to fetch electricity usage data from **Arizona Public Service (APS)** and store it as historical statistics.

Uses the [homeassistant-historical-sensor](https://github.com/ldotlopez/ha-historical-sensor) helper.

## Features
- Four sensors: Total, On-Peak, Off-Peak, Other-Peak usage (kWh)
- Full historical data
- Sensors must be manually updated each day using an automation that runs daily that executes the get_aps_data action for each sensor.
- Works with the Energy Dashboard
- Configurable username/password via UI
- Reconfigure without removing the integration
- No extra hardware required

## Installation 
1. Copy files from https://github.com/bakernigel/apsmeter/tree/main/custom_components/apsmeter into your HA custom_components directory
2. Restart Home Assistant

## Configuration
1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **APS Meter**
3. Enter your APS.com username (email) and password

## Support
- [GitHub Issues](https://github.com/bakernigel/apsmeter/issues)
