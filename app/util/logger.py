import logging, sys, os, traceback

def setup_app_logger(name="APP"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if logger.handlers: return logger
    formatter = logging.Formatter('%(asctime)s [%(name)s] [%(levelname)s] %(message)s')
    fh = logging.FileHandler("app_debug.log", mode='a', encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

def crash_handler(etype, value, tb):
    # Global hook to catch any unhandled exception
    logger = logging.getLogger("CRASH")
    error_msg = "".join(traceback.format_exception(etype, value, tb))
    logger.critical(f"UNHANDLED EXCEPTION:\n{error_msg}")
    for handler in logger.handlers: handler.flush()


class StreamToLogger:
    """File-like object that redirects writes to a logger instance."""
    def __init__(self, logger, level=logging.INFO):
        self.logger = logger
        self.level = level
        self._buffer = ''

    def write(self, buf):
        # Buffer data until newline and then emit
        self._buffer += buf
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            if line:
                self.logger.log(self.level, line)

    def flush(self):
        if self._buffer:
            self.logger.log(self.level, self._buffer)
            self._buffer = ''


def hook_std_streams(logger=None):
    """Redirect sys.stdout and sys.stderr to the provided logger.

    Pass a logger (from `setup_app_logger`) or the function will create one named 'STD'.
    """
    if logger is None:
        logger = setup_app_logger('STD')
    sys.stdout = StreamToLogger(logger, logging.INFO)
    sys.stderr = StreamToLogger(logger, logging.ERROR)