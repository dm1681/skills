from app.store import Store


class Service:
    def __init__(self) -> None:
        self.store = Store()

    def register(self, name: str):
        return self.store.add(name)

    def welcome(self, name: str) -> str:
        u = self.store.get(name)
        return u.greeting() if u else "no such user"
