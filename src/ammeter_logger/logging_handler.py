import logging
import logging.handlers
from glob import glob
from datetime import datetime, timedelta
import pathlib
import os

SYSLOG_SEVERITIES = [
    'EMERGENCY',
    'ALERT',
    'CRITICAL',
    'ERROR',
    'WARNING',
    'NOTICE',
    'INFORMATIONAL',
    'DEBUG'
]


DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL

log_level = {
    'DEBUG': logging.DEBUG,
    "INFO": logging.INFO,
    "WARNiNG": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}


def create_logger(log_file='', file_level='WARNING', console_level='WARNING', name='', file_mode='a', console=True,
                  syslog=False, syslog_script_name='', log_file_vars=[], log_file_retention_days=0, propagate=False):
    """ Creates a logger and returns the handle.
        Log file vars should be sent as a dict -> {"var": "{date}", "set": "%Y-%m-%d-%Y-%M"}

        Supported log file vars:
            {date} - will be replaced with the current date using the provided strftime format
    
     """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = propagate
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level.get(console_level.upper(), logging.WARNING))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # syslog
    if syslog:
        syslog_formatter = logging.Formatter(syslog_script_name + '[%(process)d]: %(levelname)s: %(message)s')
        syslog_handler = logging.handlers.SysLogHandler(address='/dev/log')
        syslog_handler.setLevel(log_level.get(file_level.upper(), logging.WARNING))
        syslog_handler.setFormatter(syslog_formatter)
        logger.addHandler(syslog_handler)

    # file
    if log_file != '':
        # replace variables in the log file name
        for var in log_file_vars:
            if type(var) == dict and 'var' in var and 'set' in var and var['var'] == "{date}":
                log_file = log_file.replace(var['var'], datetime.now().strftime(var['set']))
        file_handler = logging.FileHandler(log_file, mode=file_mode, encoding='utf-8', delay=False)
        file_handler.setLevel(log_level.get(file_level.upper(), logging.WARNING))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # manage retention
        if log_file_retention_days > 0:
            # replace variables with a *
            log_file_search_name = log_file
            for var in log_file_vars:
                log_file_search_name.replace(var['var'], '*')
            old_log_files = glob(log_file_search_name)
            for old_log_file in old_log_files:
                # check the age and delete if needed
                fname = pathlib.Path(old_log_file)
                mtime = datetime.fromtimestamp(fname.stat().st_mtime)
                if mtime < datetime.now() - timedelta(days=log_file_retention_days):
                    logger.info('Deleting old log file %s.  Modified time %s, retention set to %i days.', old_log_file, mtime, log_file_retention_days)
                    os.remove(old_log_file)

    # return the logger
    return logger
