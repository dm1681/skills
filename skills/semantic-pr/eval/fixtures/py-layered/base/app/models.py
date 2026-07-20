class User:
    def __init__(self, name: str) -> None:
        self.name = name

    def greeting(self) -> str:
        return "hi " + self.name


def make_user(name: str) -> User:
    return User(name)
