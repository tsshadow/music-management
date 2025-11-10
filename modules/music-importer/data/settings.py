import logging
import os
from dotenv import load_dotenv


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
    load_dotenv()

    def __init__(self):
        self.debug = os.getenv("debug")
        self.rescan = os.getenv("rescan")
        self.dryrun = os.getenv("dryrun")
        self.import_folder_path = os.getenv("import_folder_path", "")
        self.eps_folder_path = os.getenv("eps_folder_path", "")
        self.music_folder_path = os.getenv("music_folder_path", "")
        self.delimiter = os.getenv("delimiter", os.sep)

        logging.info('import_folder_path = %s', self.import_folder_path)
        logging.info('music_folder_path = %s', self.music_folder_path)
        logging.info('eps_folder_path = %s', self.eps_folder_path)
        logging.info('delimiter = %s', self.delimiter)
