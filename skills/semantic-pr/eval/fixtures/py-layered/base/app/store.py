from app.models import User, make_user


class Store:
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def add(self, name: str) -> User:
        u = make_user(name)
        self._users[u.name] = u
        return u

    def get(self, name: str) -> User | None:
        return self._users.get(name)
