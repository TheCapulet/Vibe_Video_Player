import os, time, vlc, sys, hashlib, traceback
def get_h(p): return hashlib.md5(p.lower().replace("\\","/").encode()).hexdigest()
def run():
    args = ["--intf=dummy", "--vout=dummy", "--no-audio", "--avcodec-hw=none", "--quiet"]
    try:
        inst = vlc.Instance(*args)
        p = inst.media_player_new()
    except Exception as e:
        sys.stderr.write(f"FATAL_INIT: {e}\n"); sys.stderr.flush(); return
    while True:
        line = sys.stdin.readline()
        if not line or "QUIT" in line: break
        try:
            vpath, seek = line.strip().split("|")
            tp = os.path.join("resources", "thumbs", f"{get_h(vpath)}.jpg")
            if not os.path.exists(tp):
                p.set_media(inst.media_new(vpath)); p.play()
                for _ in range(30):
                    if p.get_length() > 0: break
                    time.sleep(0.1)
                t = int(seek)*1000 if p.get_length() > int(seek)*1000 else p.get_length() // 2
                p.set_time(t); time.sleep(1.2); p.video_take_snapshot(0, tp, 320, 180)
                p.stop()
        except Exception:
            sys.stderr.write(f"TASK_ERR: {traceback.format_exc()}\n"); sys.stderr.flush()
    p.release(); inst.release()
if __name__ == "__main__":
    os.makedirs("resources/thumbs", exist_ok=True); run()