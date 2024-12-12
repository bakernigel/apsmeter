
"""
Simple implementation of the aps networks API

"""

import logging

import aiohttp
import asyncio
import requests
import urllib.parse

from datetime import datetime, timedelta
from typing import Dict, List, Optional


_LOGGER = logging.getLogger(__name__)


class API:
    """Simple APS Networks API wrapper"""

    def __init__(self):

        self._access_token = None  # type: Optional[str]
        self._refresh_token = None  # type: Optional[str]
        self._auth_expiration = None  # type: Optional[datetime]
        self._is_authed = False  # type: bool
        self._session = None
        self._peak_demand = None
        self._current_total_usage = None
        self._current_peak_hour_usage = None
        self._read_time = None
        self._usage_list = None

        self._date = None   

    async def ensure_session(self) -> aiohttp.ClientSession:
        """Ensure that we have an aiohttp ClientSession"""
        if self.websession is None:
            self.websession = aiohttp.ClientSession()
        return self.websession             

    async def _set_credentials(self, status_code: int, login_result):
        """Update the internal credentials store."""
        if status_code == 404:
            _LOGGER.error(
                  "_set_credentials login_result: %s",
                    login_result,
            )
            self._is_authed = False
            return    
        elif status_code == 401:
            _LOGGER.error(
                  "_set_credentials login_result: %s",
                    login_result,
            )
            self._is_authed = False
            return
            
        _LOGGER.debug(
                  "_set_credentials login_result: %s",
                    login_result,
        )            

        self._access_token = login_result["access_token"]
        self._refresh_token = login_result["refresh_token"]
        self._is_authed = True  # TODO: Any non 200 status code should cause this to be false
        

            
    def _set_intervalusagedata(self, status_code: int, attribute, read_result: Dict):
        """Update the internal credentials store."""
        if status_code == 404:
            _LOGGER.error(
                  "_set_billingreadusage read_result: %s",
                    read_result,
            )    
        elif status_code == 401:
            _LOGGER.error(
                  "_set_billingreadusage read_result: %s",
                    read_result,
            )    
        
        if read_result["summarizedUsageDataResponse"]["currentTotalUsage"] == None:
            _LOGGER.error(
                  "Get intervalusagedata got no data",
                   read_result,
            )        
            return
        
        date = self._date.strftime("%Y-%m-%d")

        my_list =[]
        
        attribute_to_estimated = {
            "onPeakUsage": {
                True: "onPeakUsage",
                False: "onPeakEstimated",
            },
            "offPeakUsage": {
                True: "offPeakUsage",
                False: "offPeakEstimated",
            },
            "otherPeakUsage": {
                True: "otherPeakUsage",
                False: "otherPeakEstimated",
            },
            "totalUsage": {
                True: "totalUsage",
                False: "totalUsage",
            }
        }
        
        for i in range(0, 24):

            time = read_result["summarizedUsageDataResponse"]["dailyRatePlanUsage"][i]["time"]
            is_actual = read_result["summarizedUsageDataResponse"]["dailyRatePlanUsage"][i]["isActual"]
            if is_actual == False:
                _LOGGER.warning("Using estimated values for %s on %s:%s",
                   attribute,
                   date,
                   time,
                )
            new_attribute = attribute_to_estimated[attribute][is_actual]

            usage = read_result["summarizedUsageDataResponse"]["dailyRatePlanUsage"][i][new_attribute]
            date_time = date + time
            date_time_obj = datetime.strptime(date_time, "%Y-%m-%d%I:%M %p")
# Add 1 hour. Sensor async_calculate_statistic_data expects the time to be the end of the hour. APS provides the beginning of the hour.            
            date_time_obj = date_time_obj + timedelta(hours=1)

            if usage != None:           
                my_list.append((date_time_obj,usage))
            else:
                _LOGGER.debug("Found usage==None for %s on %s:%s",
                   attribute,
                   date,
                   time,
                )                 
    

        self._usage_list = my_list 
                
        _LOGGER.warning(
                  "_usage_list for %s is %s",
                   attribute,
                   my_list,
        )              
     
     
    async def async_sign_in(self):
        """Authenticate to APS API asynchronously."""

        url = "https://www.aps.com/api/Mobile/User/Authenticate"

        payload = {"username":"bakernigel","password":"N9ZKxWI/00OUBuXEss+TRayR9rfvvMAOn4IJyHlU7zCcIU84t0scmbR7HxnwQVHNOfTVNMnWuy0cUH2p1XsQUBuOmFmvfU0r/BuITxGL54oLvI4EBjqC5g+XkrzX6y7UbQIHmcUHevjwXXG2TPe+nibFIFScUrTd3qEqa3T1Snp6ejN5psUdvvg58Mv6x2Xc0KKZT3YkSb+pzQkgo8F/Cm1eR6PkYlBslZAW7exkDXdH94nsb0Qbvo7QtgiN1X/pNIzFRK8mhkQFMMnfqZsqqmGLodgCpfGMw+dXu+Ok2wiEuj00aQtEw+FFUAIHQJejEZubBCVWvvhWStgh1IMi8Q=="}    

        headers = {
            "accept": "*/*",
            "content-type": "application/json"
        }
        
        self._session = aiohttp.ClientSession()
        session = self._session      
        
        async with session.post(url, json=payload, headers=headers) as resp:
            buff = await resp.json(content_type=None)
            _LOGGER.debug(
                  "buff %s",
                   buff,
            )                          
            await self._set_credentials(resp.status,  buff)

            

            
    async def async_get_intervalusagedata(self,attribute):
        if self._is_authed == False:
            _LOGGER.error("Attempt to get_intervalusagedata when login failed")
            return                                  
             
        url = "https://mobi.aps.com/customeraccountservices/v1/getintervalusagedata"
	
        date = self._date.strftime('%Y-%m-%d')
	 		 	
        payload = {
            "cssUser":"MOBAPP",
	    "userName":"bakernigel",
	    "saId":"0653330312",
	    "accountId":"0655501526",
	    "premiseId":"7190353053",
	    "billCycleStartDate":date,
	    "billCycleEndDate":date,
	    "prodMeterNumber":"",
	    "isPremiseUsageRequestedForProdMeter":"false",
	    "receivedUsageDataForProdMeter":"false",
	    "utilityMeterNumber":"EU1517",
	    "isPremiseUsageRequestedForUtilityMeter":"false",
	    "receivedUsageDataForUtilityMeter":"false",
	    "displayType":"D","intervals":"1",
	    "ratePlan":
	        [{"servicePlan":"R3-47",
	        "startDate":date,
	        "endDate":date}]
	}
		
        headers = {
	    "accept": "*/*",
	    "content-type": "application/json",
	    "authorization": self._access_token,
	# "x-correlation-id": "23526ff9-e116-4598-95c3-247bc6c6e166",
	# "origin": "https://www.aps.com",
	"ocp-apim-subscription-key": "d2e9aafca6d546cd9097a3e3072cd7a5",
	}

        session = self._session      
        
        async with session.post(url, json=payload, headers=headers) as resp:
            buff = await resp.json(content_type=None)
            self._set_intervalusagedata(resp.status,attribute,  buff)
                           
            
    async def async_close(self):
        session = self._session      
        await session.close()
        
    async def fetch(
        self,
        attr_name,
        start: datetime | None = None,
        end: datetime | None = None,
        step: timedelta | None = timedelta(hours=1),
    ) -> list[tuple[datetime, float]]:
    

        
        self._date = start
                      
        await self.async_sign_in()
        
        if attr_name == "aps_total_usage":
            attribute = "totalUsage"
        if attr_name == "aps_onpeak_usage":
           attribute = "onPeakUsage"
        if attr_name == "aps_offpeak_usage":
           attribute = "offPeakUsage"           
        if attr_name == "aps_otherpeak_usage":
           attribute = "otherPeakUsage"                      
        
        _LOGGER.warning(
                  "Fetch called for attr_name:%s attribute:%s Start Date: %s",
                  attr_name,
                  attribute,
                  start,
        )  
        
        
        await self.async_get_intervalusagedata(attribute)
        await self.async_close()
        
        return self._usage_list      
