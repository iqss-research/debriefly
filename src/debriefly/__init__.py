from importlib.resources import files
import logging.config
import debriefly
from debriefly.configuration import Config

__version__ = "0.6.6"


logging.config.dictConfig(
    {
        "version": 1,
        "formatters": {
            "standard": {
                "format": "(%(levelname)s) (%(filename)s) (%(asctime)s) %(message)s",
                "datefmt": "%d-%b-%y %H:%M:%S",
            }
        },
        "handlers": {
            "default": {
                "level": "NOTSET",
                "formatter": "standard",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {"": {"handlers": ["default"], "level": "INFO"}},
    }
)

config = Config("ads", files(debriefly) / "config.yaml")
