import logging
import logging.config
import sys
import os
import json
from datetime import datetime
from pathlib import Path
import traceback

from vitis_paths import currentdir, LOG_PATH


APP_LOGGER_NAME = 'Vitis Workspace Builder'
APP_LOGGER_FILE = 'workspace_builder.log'

FATAL = logging.FATAL
CRITICAL = logging.CRITICAL
ERROR = logging.ERROR
WARNING = logging.WARNING
WARN = logging.WARNING
INFO = logging.INFO
DEBUG = logging.DEBUG
TRACE = 5
NOTSET = logging.NOTSET

LOG_LEVEL = DEBUG


class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class BaseLogger(object, metaclass = Singleton):

    def __init__(self) -> None:
        logging.TRACE = TRACE
        logging.addLevelName(TRACE, "TRACE")
        def trace(self, message, *args, **kws):
            if self.isEnabledFor(logging.TRACE):
                self._log(TRACE, message, args, **kws)
        logging.Logger.trace = trace
        logger = logging.getLogger(APP_LOGGER_NAME)

        latest_path = os.path.join(LOG_PATH, APP_LOGGER_FILE)
        Path(LOG_PATH).mkdir(parents=True, exist_ok=True)

        simple_fmt = logging.Formatter(
            fmt="[%(asctime)s] %(levelname)s - %(name)s | %(message)s", 
            datefmt="%H:%M:%S"
        )
        verbose_fmt = logging.Formatter(
            fmt="[%(asctime)s] %(levelname)s - %(name)s - %(threadName)s - %(funcName)s:%(lineno)d | %(message)s", 
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        self._console = logging.StreamHandler()
        self._console.setLevel(LOG_LEVEL)
        self._console.setFormatter(simple_fmt)

        self._file = logging.FileHandler(latest_path)
        self._file.setLevel(LOG_LEVEL)
        self._file.setFormatter(verbose_fmt)

        self._logger = logger
        sys.excepthook = exception_handler

    def get_logger(self, module_name):
        logger = logging.getLogger(APP_LOGGER_NAME).getChild(module_name)
        logger.addHandler(self._console)
        logger.addHandler(self._file)
        logger.setLevel(LOG_LEVEL)
        return logger


class Logger(object):

    level_map = {
        'FATAL': FATAL,
        'CRITICAL': CRITICAL,
        'ERROR': ERROR,
        'WARNING': WARNING,
        'WARN': WARN,
        'INFO': INFO,
        'DEBUG': DEBUG,
        'TRACE': TRACE,
        'NOTSET': NOTSET
    }

    def __init__(self, module_name) -> None:
        self.base_logger = BaseLogger()
        self.logger = self.base_logger.get_logger(module_name)

    def log(self, level, msg):
        if level in self.level_map.values():
            self.logger.log(level, msg)
        elif level in self.level_map.keys():
            self.logger.log(self.level_map[level], msg)
        else:
            self.logger.log(NOTSET, msg)

    def get_base_logger(self, name):
        return logging.getLogger(name)

    def fatal(self, msg):
        self.logger.log(FATAL, msg)

    def critical(self, msg):
        self.logger.log(CRITICAL, msg)

    def error(self, msg):
        self.logger.log(ERROR, msg)

    def warning(self, msg):
        self.logger.log(WARNING, msg)

    def warn(self, msg):
        self.logger.log(WARN, msg)

    def info(self, msg):
        self.logger.log(INFO, msg)

    def debug(self, msg):
        self.logger.log(DEBUG, msg)

    def trace(self, msg):
        self.logger.log(TRACE, msg)


def cleanupLatestLog():
    latest_path = os.path.join(LOG_PATH, APP_LOGGER_FILE)
    latest_path = latest_path.replace("/", "\\")
    open(latest_path, 'w').close()


def exception_handler(type, value, tb):
    logger = logging.getLogger(APP_LOGGER_NAME)
    for line in traceback.TracebackException(type, value, tb).format(chain=True):
        logger.exception(line)
    logger.exception(value)
    sys.__excepthook__(type, value, tb)
