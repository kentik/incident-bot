import config
import ipaddress
import random
import string

from datetime import datetime
from pytz import timezone
from typing import Any, List

logger = config.log.get_logger("shared")

random_suffix = "".join(
    random.choices(string.ascii_lowercase + string.digits, k=6)
)
timestamp_fmt = "%Y-%m-%dT%H:%M:%S %Z"
timestamp_fmt_short = "%d/%m/%Y %H:%M:%S %Z"

application_timezone = timezone(config.active.options.get("timezone"))


def db_timestamp(ts: datetime) -> str:
    if ts.tzinfo:
        if ts.tzinfo != application_timezone:
            return ts.astimezone(application_timezone).strftime(timestamp_fmt_short)
        else:
            return ts.strftime(timestamp_fmt_short)
    else:
        return application_timezone.localize(ts).strftime(timestamp_fmt_short)


def fetch_timestamp(short: bool = False):
    """Return a localized, formatted timestamp using datetime.now()"""
    now = datetime.now(tz=application_timezone)
    if short:
        return now.strftime(timestamp_fmt_short)
    return now.strftime(timestamp_fmt)


def fetch_timestamp_from_time_obj(t: datetime):
    """Return a localized, formatted timestamp using datetime.datetime class"""
    return application_timezone.localize(t).strftime(timestamp_fmt)


def find_index_in_list(lst: List, key: Any, value: Any):
    """Takes a list of dictionaries and returns
    the index value if key matches.
    """
    for i, dic in enumerate(lst):
        if dic[key] == value:
            return i
    return -1


def validate_ip_address(address: str) -> bool:
    """Validate that a provided string is an IP address"""
    try:
        ipaddress.ip_network(address)
        return True
    except ValueError as error:
        logger.error(error)
        return False


def validate_ip_in_subnet(address: str, subnet: str) -> bool:
    """Return whether or not an IP address is within a subnet"""
    return ipaddress.ip_address(address) in ipaddress.ip_network(subnet)
