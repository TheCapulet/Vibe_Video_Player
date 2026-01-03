class Player:
    def __init__(self, backend):
        self._backend = backend

    def load_media(self, path: str):
        self._backend.open_media(path)

    def play(self):
        self._backend.play()

    def pause(self):
        self._backend.pause()

    def seek(self, ms: int):
        self._backend.set_position(ms)

    def set_volume(self, volume: float):
        self._backend.set_volume(int(volume * 100))