import vlc, threading, time
from app.util.logger import setup_app_logger

class VLCBackend:
    def __init__(self):
        self.log = setup_app_logger("VLCBackend")
        self.lock = threading.Lock()
        try:
            self.main_inst = vlc.Instance("--quiet", "--no-osd")
            self.main_player = self.main_inst.media_player_new()
            self.main_player.video_set_mouse_input(False)
            self.main_player.video_set_key_input(False)
            self.prev_inst = vlc.Instance("--quiet", "--no-audio", "--no-osd", "--avcodec-hw=none")
            self.prev_player = self.prev_inst.media_player_new()
            self.prev_player.video_set_mouse_input(False)
            self.ready = True
        except Exception:
            self.log.exception("Failed to initialize libvlc instances")
            self.ready = False

    def get_state_safe(self):
        try:
            return self.main_player.get_state() if self.ready else 0
        except Exception:
            self.log.debug("get_state_safe failed", exc_info=True)
            return 0

    def attach_main(self, h):
        if self.ready:
            try:
                self.main_player.set_hwnd(h)
            except Exception:
                self.log.exception("attach_main failed")

    def attach_prev(self, h):
        if self.ready:
            try:
                self.prev_player.set_hwnd(h)
            except Exception:
                self.log.exception("attach_prev failed")

    def open_main(self, p):
        if not self.ready:
            self.log.debug("open_main called but backend not ready")
            return
        with self.lock:
            try:
                self.main_player.set_media(self.main_inst.media_new(p))
                self.main_player.play()
            except Exception:
                self.log.exception("open_main failed for %s", p)

    # Compatibility wrapper used by higher-level Player class
    def open_media(self, p):
        return self.open_main(p)

    def play(self):
        if self.ready:
            try:
                self.main_player.play()
            except Exception:
                self.log.exception("play failed")

    def pause(self):
        if self.ready:
            try:
                self.main_player.pause()
            except Exception:
                self.log.exception("pause failed")

    def set_position(self, ms: int):
        if self.ready:
            try:
                self.main_player.set_time(ms)
            except Exception:
                self.log.exception("set_position failed")

    def open_prev(self, p, start_sec=0):
        if not self.ready:
            self.log.debug("open_prev called but backend not ready")
            return
        threading.Thread(target=self._exec_prev, args=(p, start_sec), daemon=True).start()

    def _exec_prev(self, p, s):
        with self.lock:
            try:
                self.prev_player.stop()
                self.prev_player.set_media(self.prev_inst.media_new(p))
                self.prev_player.play()
                for _ in range(10):
                    if self.prev_player.get_length() > 0:
                        break
                    time.sleep(0.05)
                self.prev_player.set_time(s * 1000)
                self.prev_player.audio_set_mute(True)
            except Exception:
                self.log.exception("preview execution failed for %s", p)

    def stop_prev(self):
        if self.ready:
            try:
                with self.lock:
                    self.prev_player.stop()
            except Exception:
                self.log.exception("stop_prev failed")

    def set_vol(self, v):
        if self.ready:
            try:
                self.main_player.audio_set_volume(v)
            except Exception:
                self.log.exception("set_vol failed with %s", v)

    def set_volume(self, v: int):
        # Accepts 0-100 integer
        return self.set_vol(v)

    def release(self):
        if self.ready:
            try:
                self.main_player.stop(); self.prev_player.stop()
                self.main_inst.release(); self.prev_inst.release()
            except Exception:
                self.log.exception("release failed")