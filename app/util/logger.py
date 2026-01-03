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