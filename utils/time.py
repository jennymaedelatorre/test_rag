from datetime import datetime
import pytz

# Define the target time zone 
PHILIPPINE_TIMEZONE = pytz.timezone('Asia/Manila')

def get_ph_time_from_utc(utc_datetime: datetime) -> datetime:
    """
    Converts a naive UTC datetime object (from the database) 
    to a timezone-aware Philippine Standard Time datetime object.
    """
    if utc_datetime is None:
        return None
    
    utc_aware_datetime = pytz.utc.localize(utc_datetime)
    
    #  Convert to the Philippine time zone
    return utc_aware_datetime.astimezone(PHILIPPINE_TIMEZONE)