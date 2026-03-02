"""
Simple implementation of the aps networks API
"""
import logging
import aiohttp
import re
import base64
from datetime import datetime, timedelta
from typing import Dict, Optional

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

"""Exceptions."""
class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


def extract_rsa_key(js_content: str) -> str:
    """Extract the RSA public key from the APS JS file."""
    pattern = r'APSCOMWebPasswordpublicKey:"(-----BEGIN PUBLIC KEY-----.*?-----END PUBLIC KEY-----)"'
    match = re.search(pattern, js_content, re.DOTALL)
    if match:
        rsa_key = match.group(1)
        formatted_key = re.sub(
            r"(-----BEGIN PUBLIC KEY-----)(.*)(-----END PUBLIC KEY-----)",
            r"\1\n\2\n\3",
            rsa_key,
            flags=re.DOTALL,
        )
        return formatted_key
    else:
        raise CannotConnect("The RSA public key was not found.")


def js_encrypt(pub_key: str, text: str) -> str:
    """JSEncrypt-like encryption function using cryptography."""
    rsakey = serialization.load_pem_public_key(pub_key.encode())
    if isinstance(rsakey, rsa.RSAPublicKey):
        cipher_text = rsakey.encrypt(text.encode(), padding.PKCS1v15())
        cipher_text_base64 = base64.b64encode(cipher_text)
        return cipher_text_base64.decode()
    else:
        print("Could not find public key to encrypt password.")


_LOGGER = logging.getLogger(__name__)


class API:
    """Simple APS Networks API wrapper - Singleton so login state persists"""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
                
    def __init__(self, username: str | None = None, password: str | None = None):
        """Initialize only on first creation (singleton)."""
        if getattr(self, "_initialized", False):
            # Allow config_flow test to update credentials
            if username is not None:
                self._username = username
            if password is not None:
                self._password = password
            return

        self._initialized = True        
        
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._auth_expiration: Optional[datetime] = None
        self._is_authed: bool = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._account_id: Optional[str] = None
        self._username: Optional[str] = None
        self._sa_id: Optional[str] = None
        self._premise_id: Optional[str] = None
        self._utility_meter_number: Optional[str] = None
        self._service_plan: Optional[str] = None
        self._usage_list: Optional[list] = None
        self._date: Optional[datetime] = None
        
        self._username: Optional[str] = username
        self._password: Optional[str] = password

        _LOGGER.info("APS _init called (singleton) Username: %s",self._username )

    async def ensure_session(self) -> aiohttp.ClientSession:
        """Ensure we have an open aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _set_intervalusagedata(self, status_code: int, attribute, read_result: Dict):
        """Update the internal credentials store."""
        if status_code in (404, 401):
            _LOGGER.error("_set_intervalusagedata read_result: %s", read_result)
            return

        data = read_result.get("summarizedUsageDataResponse", {})
        if data.get("currentTotalUsage") is None:
            _LOGGER.error("Get intervalusagedata got no data: %s", read_result)
            return

        date = self._date.strftime("%Y-%m-%d")
        my_list = []

        attribute_to_estimated = {
            "onPeakUsage": {True: "onPeakUsage", False: "onPeakEstimated"},
            "offPeakUsage": {True: "offPeakUsage", False: "offPeakEstimated"},
            "otherPeakUsage": {True: "otherPeakUsage", False: "otherPeakEstimated"},
            "totalUsage": {True: "totalUsage", False: "totalUsage"},
        }

        for i in range(24):
            daily = data["dailyRatePlanUsage"][i]
            time = daily["time"]
            is_actual = daily["isActual"]

            if not is_actual:
                _LOGGER.warning("Using estimated values for %s on %s:%s", attribute, date, time)

            new_attr = attribute_to_estimated[attribute][is_actual]
            usage = daily[new_attr]

            dt_str = date + time
            dt_obj = datetime.strptime(dt_str, "%Y-%m-%d%I:%M %p") + timedelta(hours=1)

            if usage is not None:
                my_list.append((dt_obj, usage))
            else:
                _LOGGER.debug("Found usage==None for %s on %s:%s", attribute, date, time)

        self._usage_list = my_list
        _LOGGER.info("_usage_list for %s is %s", attribute, my_list)

    async def async_sign_in(self):
        """Authenticate to APS API asynchronously."""

        if not self._username or not self._password:
            raise InvalidAuth("Username or password not set in config flow")

        username = self._username
        password = self._password

        _LOGGER.info("Starting login process for Arizona Public Service (APS)")

        session = await self.ensure_session()
        session.cookie_jar.clear(lambda cookie: cookie["domain"] == "www.aps.com")

        # Get public RSA key
        async with session.get(
            "https://www.aps.com/Assets/Js/aps-apscom.js",
            headers={"User-Agent": USER_AGENT},
            raise_for_status=True,
        ) as resp:
            js_content = await resp.text()

        rsa_key_text = extract_rsa_key(js_content)
        encrypted_password = js_encrypt(rsa_key_text, password)

        # Login POST
        async with session.post(
            "https://www.aps.com/api/sitecore/SitecoreReactApi/UserAuthentication",
            json={"username": username, "password": encrypted_password},
            raise_for_status=True,
        ) as resp:
            login_result = await resp.json(content_type=None)   # ? APS can return weird headers
            if not login_result.get("isLoginSuccess"):
                raise InvalidAuth("Username and password failed")

        # Get All User Details 
        async with session.get(
            "https://www.aps.com/api/sitecore/sitecorereactapi/GetAllUserDetails",
            raise_for_status=True,
        ) as resp:
            # APS returns "application /json" (with space!) ? use content_type=None
            user_details = await resp.json(content_type=None)

            details = user_details.get("Details", {})
            account_response = (
                details.get("AccountDetails", {})
                .get("getAccountDetailsResponse", {})
                .get("getAccountDetailsRes", {})
            )
            person_details = account_response.get("getPersonDetails", {})
            sasp_data = account_response.get("getSASPListByAccountID", {})
            premise_list = sasp_data.get("premiseDetailsList", [])

            self._account_id = person_details.get("accountID")
            self._username = username

            if premise_list:
                premise = premise_list[0]
                sasp_details = premise.get("sASPDetails", [{}])[0] if premise.get("sASPDetails") else {}

                self._sa_id = sasp_details.get("sAID")
                self._premise_id = (
                    premise.get("premiseID") or premise.get("premiseId") or premise.get("premiseNumber")
                )
                self._utility_meter_number = (
                    sasp_details.get("utilityMeterNumber")
                    or sasp_details.get("meterNumber")
                    or premise.get("utilityMeterNumber")
                    or premise.get("meterNumber")
                )
                self._service_plan = (
                    premise.get("servicePlan")
                    or sasp_details.get("servicePlan")
                    or "R3-47"
                )

            profile_data = details.get("profileData", {})
            self._access_token = profile_data.get("access_token")
            self._refresh_token = profile_data.get("refresh_token")

            _LOGGER.info(
                "? Extracted APS account info ? AccountID:%s SAID:%s PremiseID:%s Meter:%s Plan:%s",
                self._account_id, self._sa_id, self._premise_id,
                self._utility_meter_number, self._service_plan,
            )

        self._is_authed = True
        self._auth_expiration = datetime.now() + timedelta(minutes=55)
        _LOGGER.info("APS login successful - token valid until %s", self._auth_expiration)

    async def async_get_intervalusagedata(self, attribute):
        if not self._is_authed:
            _LOGGER.error("Attempt to get_intervalusagedata when not authenticated")
            return

        url = "https://mobi.aps.com/customeraccountservices/v1/getintervalusagedata"
        date = self._date.strftime("%Y-%m-%d")

        payload = {
            "cssUser": "MOBAPP",
            "userName": self._username.split("@")[0] if self._username else "bakernigel",
            "saId": self._sa_id or "0653330312",
            "accountId": self._account_id or "0655501526",
            "premiseId": self._premise_id or "7190353053",
            "billCycleStartDate": date,
            "billCycleEndDate": date,
            "prodMeterNumber": "",
            "isPremiseUsageRequestedForProdMeter": "false",
            "receivedUsageDataForProdMeter": "false",
            "utilityMeterNumber": self._utility_meter_number or "EU1517",
            "isPremiseUsageRequestedForUtilityMeter": "false",
            "receivedUsageDataForUtilityMeter": "false",
            "displayType": "D",
            "intervals": "1",
            "ratePlan": [{"servicePlan": self._service_plan or "R3-47", "startDate": date, "endDate": date}],
        }

        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "authorization": self._access_token,
            "ocp-apim-subscription-key": "d2e9aafca6d546cd9097a3e3072cd7a5",
        }

        session = await self.ensure_session()
        async with session.post(url, json=payload, headers=headers) as resp:
            buff = await resp.json(content_type=None)
            self._set_intervalusagedata(resp.status, attribute, buff)

    async def async_close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch(
        self,
        attr_name,
        start: datetime | None = None,
        end: datetime | None = None,
        step: timedelta | None = timedelta(hours=1),
    ) -> list[tuple[datetime, float]]:
        self._date = start

        if (
            not self._is_authed
            or self._auth_expiration is None
            or datetime.now() > self._auth_expiration
        ):
            _LOGGER.info("APS authentication expired or missing ? logging in now")
            await self.async_sign_in()
        else:
            _LOGGER.debug("Re-using existing APS session (expires %s)", self._auth_expiration)

        if attr_name == "aps_total_usage":
            attribute = "totalUsage"
        elif attr_name == "aps_onpeak_usage":
            attribute = "onPeakUsage"
        elif attr_name == "aps_offpeak_usage":
            attribute = "offPeakUsage"
        elif attr_name == "aps_otherpeak_usage":
            attribute = "otherPeakUsage"
        else:
            attribute = "totalUsage"

        _LOGGER.info(
            "Fetch called for attr_name:%s attribute:%s Start Date: %s",
            attr_name, attribute, start,
        )

        await self.async_get_intervalusagedata(attribute)
        return self._usage_list