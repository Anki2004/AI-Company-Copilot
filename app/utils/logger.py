import json
import logging
from datetime import datetime
logging.basicConfig(
    level = logging.INFO,
    format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

)
logger = logging.getLogger("copilot")

def log_execution(event_type:str, data:dict):
    log_entry = {
        "timestamp":datetime.now().isoformat(),
        "event":event_type,
        "data":data
    }

    logger.info(json.dumps(log_entry))
    