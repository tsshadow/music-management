import logging

from api.config_store import ConfigStore


class SingletonMeta(type):
    """
    The Singleton class can be implemented in different ways in Python. Some
    possible methods include: base class, decorator, metaclass. We will use the
    metaclass because it is best suited for this purpose.
    """

    _instances = {}

    def __call__(cls, *args, **kwargs):
        """
        Possible changes to the value of the `__init__` argument do not affect
        the returned instance.
        """
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class Settings(metaclass=SingletonMeta):
    def __init__(self):
        self._store = ConfigStore()
        self._keys = [
            "debug",
            "rescan",
            "dryrun",
            "import_folder_path",
            "eps_folder_path",
            "music_folder_path",
            "delimiter",
        ]
        self._subscriptions = []
        self._refresh()
        for key in self._keys:
            self._subscriptions.append(
                self._store.subscribe(key, lambda value, attr=key: self._update(attr, value))
            )

        logging.info('import_folder_path = %s', self.import_folder_path)
        logging.info('music_folder_path = %s', self.music_folder_path)
        logging.info('eps_folder_path = %s', self.eps_folder_path)
        logging.info('delimiter = %s', self.delimiter)

    def _refresh(self) -> None:
        values = self._store.get_many(self._keys)
        for key, value in values.items():
            setattr(self, key, value)

    def _update(self, attribute: str, value):
        setattr(self, attribute, value)
