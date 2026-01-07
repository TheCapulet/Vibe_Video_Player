import os, time, vlc, sys, hashlib, traceback, logging, socket, signal
from pathlib import Path

# Try to import the project's logger. If the worker is started with a different
# working directory (or as a standalone script) the `app` package may not be
# importable. In that case fall back to a basic logger and ensure the project
# root is on sys.path for relative imports that expect it.
try:
    from app.util.logger import setup_app_logger
    logger = setup_app_logger("WORKER")
except Exception:
    # Ensure repository root is on sys.path (worker.py is in app/util)
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("WORKER")

def get_h(p):
    return hashlib.md5(p.lower().replace("\\","/").encode()).hexdigest()

def run():
    args = ["--intf=dummy", "--vout=dummy", "--no-audio", "--avcodec-hw=none", "--quiet"]
    try:
        inst = vlc.Instance(*args)
        p = inst.media_player_new()
    except Exception as e:
        logger.critical("FATAL_INIT: %s", e)
        return
    # Determine whether an IPC port was provided; if so, use a TCP socket server on localhost.
    ipc_port = None
    for a in sys.argv[1:]:
        if a.startswith("--ipc-port="):
            try:
                ipc_port = int(a.split("=", 1)[1])
            except Exception:
                ipc_port = None
    # Track running state so signal handlers can request shutdown
    running = True
    def _handle_term(signum, frame):
        nonlocal running
        running = False
        logger.info("Received termination signal %s, shutting down worker loop", signum)

    # Install signal handlers for graceful shutdown where available
    try:
        signal.signal(signal.SIGTERM, _handle_term)
        signal.signal(signal.SIGINT, _handle_term)
    except Exception:
        # Some platforms (Windows) may have limited signal support; ignore failures
        pass

    if ipc_port:
        logger.info("Worker ready, listening for input lines on tcp://127.0.0.1:%s", ipc_port)
        # create listening socket
        serversock = None
        try:
            serversock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            serversock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            serversock.bind(('127.0.0.1', ipc_port))
            serversock.listen(1)
            # set a short accept timeout so we can observe termination requests
            try:
                serversock.settimeout(1.0)
            except Exception:
                pass
        except Exception:
            logger.exception("Failed to create IPC server socket on port %s", ipc_port)
            serversock = None

        while running:
            if serversock is None:
                time.sleep(1)
                continue
            try:
                try:
                    conn, addr = serversock.accept()
                except socket.timeout:
                    # timeout regularly to check `running`
                    continue
            except Exception:
                logger.exception("Accept failed on IPC socket")
                time.sleep(0.2)
                continue
            logger.info("Accepted IPC connection from %s", addr)
            try:
                with conn:
                    f = conn.makefile('r', encoding='utf-8', errors='replace')
                    for line in f:
                        if not running:
                            logger.info("Shutting down connection loop due to stop request")
                            break
                        if not line:
                            break
                        if "QUIT" in line:
                            running = False
                            break
                        try:
                            logger.debug("Worker received raw line: %r", line)
                            if line.strip().startswith("__DIAG_PING__"):
                                logger.info("Received diagnostic ping, ignoring")
                                continue
                            vpath, seek = line.strip().split("|")
                            tp = os.path.join("resources", "thumbs", f"{get_h(vpath)}.jpg")
                            logger.debug("Computed thumb path %s for video %s (seek %s)", tp, vpath, seek)
                            if not os.path.exists(tp):
                                try:
                                    p.set_media(inst.media_new(vpath))
                                    p.play()
                                except Exception:
                                    logger.exception("Failed to set media/play for %s", vpath)
                                    continue
                                for _ in range(30):
                                    if p.get_length() > 0:
                                        break
                                    time.sleep(0.1)
                                t = int(seek) * 1000 if p.get_length() > int(seek) * 1000 else p.get_length() // 2
                                try:
                                    logger.debug("Setting time %s ms and taking snapshot to %s", t, tp)
                                    p.set_time(t)
                                    time.sleep(1.2)
                                    p.video_take_snapshot(0, tp, 320, 180)
                                    p.stop()
                                    logger.info("Snapshot written: %s", tp)
                                except Exception:
                                    logger.exception("Snapshot failed for %s -> %s", vpath, tp)
                        except Exception:
                            logger.exception("TASK_ERR while processing line: %s", line)
            except Exception:
                logger.exception("IPC connection handling error")
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        # close server socket on exit
        try:
            if serversock is not None:
                serversock.close()
        except Exception:
            pass
        # end socket server loop
    else:
        logger.info("Worker ready, listening for input lines on stdin")
        while True and running:
            # read raw line from stdin (worker process may be run with binary stdin)
            try:
                line = sys.stdin.readline()
            except Exception:
                # If reading from stdin fails, log and break
                logger.exception("Failed to read from stdin, exiting worker")
                break
            if not line or "QUIT" in line:
                break
            try:
                logger.debug("Worker received raw line: %r", line)
                # Ignore diagnostic ping lines sent by the parent process
                if line.strip().startswith("__DIAG_PING__"):
                    logger.info("Received diagnostic ping, ignoring")
                    continue
                vpath, seek = line.strip().split("|")
                tp = os.path.join("resources", "thumbs", f"{get_h(vpath)}.jpg")
                logger.debug("Computed thumb path %s for video %s (seek %s)", tp, vpath, seek)
                if not os.path.exists(tp):
                    try:
                        p.set_media(inst.media_new(vpath))
                        p.play()
                    except Exception:
                        logger.exception("Failed to set media/play for %s", vpath)
                        continue
                    for _ in range(30):
                        if p.get_length() > 0:
                            break
                        time.sleep(0.1)
                    t = int(seek) * 1000 if p.get_length() > int(seek) * 1000 else p.get_length() // 2
                    try:
                        logger.debug("Setting time %s ms and taking snapshot to %s", t, tp)
                        p.set_time(t)
                        time.sleep(1.2)
                        p.video_take_snapshot(0, tp, 320, 180)
                        p.stop()
                        logger.info("Snapshot written: %s", tp)
                    except Exception:
                        logger.exception("Snapshot failed for %s -> %s", vpath, tp)
            except Exception:
                logger.exception("TASK_ERR while processing line: %s", line)
    try:
        p.release()
        inst.release()
    except Exception:
        logger.exception("Error releasing vlc resources")

if __name__ == "__main__":
    os.makedirs("resources/thumbs", exist_ok=True)
    run()