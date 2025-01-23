from enum import Enum, auto


class CrudOperation(Enum):
    Create = auto()
    Read = auto()
    Update = auto()
    Delete = auto()
