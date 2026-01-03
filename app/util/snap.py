import os, time, vlc, sys, hashlib
def get_h(p): return hashlib.md5(p.lower().replace("\\","/").encode()).hexdigest()
def snap():
    if len(sys.argv) < 3: return
    vpath, seek = sys.argv[1], int(sys.argv[2])
    tp = os.path.join("resources","thumbs",f"{get_h(vpath)}.jpg")
    if os.path.exists(tp): return
    os.makedirs(os.path.dirname(tp), exist_ok=True)
    i = vlc.Instance("--intf=dummy","--vout=dummy","--no-audio","--avcodec-hw=none","--quiet")
    p = i.media_player_new(); p.set_media(i.media_new(vpath)); p.play()
    for _ in range(30):
        if p.get_length() > 0: break
        time.sleep(0.1)
    t = seek*1000 if p.get_length() > seek*1000 else p.get_length()//2
    p.set_time(t); time.sleep(1.2); p.video_take_snapshot(0, tp, 320, 180)
    p.stop(); p.release(); i.release()
if __name__ == "__main__":
    snap()