import vlc, threading, time
class VLCBackend:
    def __init__(self):
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
        except: self.ready = False
    def get_state_safe(self):
        try: return self.main_player.get_state() if self.ready else 0
        except: return 0
    def attach_main(self, h): 
        if self.ready: self.main_player.set_hwnd(h)
    def attach_prev(self, h): 
        if self.ready: self.prev_player.set_hwnd(h)
    def open_main(self, p):
        if not self.ready: return
        with self.lock:
            self.main_player.set_media(self.main_inst.media_new(p))
            self.main_player.play()
    def open_prev(self, p, start_sec=0):
        if not self.ready: return
        threading.Thread(target=self._exec_prev, args=(p, start_sec), daemon=True).start()
    def _exec_prev(self, p, s):
        with self.lock:
            try:
                self.prev_player.stop()
                self.prev_player.set_media(self.prev_inst.media_new(p))
                self.prev_player.play()
                for _ in range(10):
                    if self.prev_player.get_length() > 0: break
                    time.sleep(0.05)
                self.prev_player.set_time(s * 1000)
                self.prev_player.audio_set_mute(True)
            except: pass
    def stop_prev(self):
        if self.ready:
            with self.lock: self.prev_player.stop()
    def set_vol(self, v): 
        if self.ready: self.main_player.audio_set_volume(v)
    def release(self):
        if self.ready:
            self.main_player.stop(); self.prev_player.stop()
            self.main_inst.release(); self.prev_inst.release()