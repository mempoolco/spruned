from multiprocessing import Manager
from multiprocessing.managers import State


def get_manager():
    if not get_manager.manager:
        get_manager.manager = Manager()
        if get_manager.manager._state.value != State.STARTED:
            get_manager.manager.start()
    return get_manager.manager


get_manager.manager = None
