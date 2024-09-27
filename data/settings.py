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
    import_folder_path = ''
    eps_folder_path = ''
    delimiter = ''

    def __init__(self):
        self.rescan = None

    def initialize(self, environment, rescan):
        print('Initializing settings for ' + environment)
        if environment == 'docker':
            self.import_folder_path = "/music/__TODO"
            self.eps_folder_path = "/music"
            self.music_folder_path = self.eps_folder_path
            self.delimiter = '/'
        elif environment == 'test':
            self.delimiter = '\\'
            self.import_folder_path = "D:\\test\\import"
            self.eps_folder_path = "D:\\test"
            self.music_folder_path = self.eps_folder_path
        else:
            self.import_folder_path = "\\\\192.0.2.2\\Music\\Eps\\__TODO"
            self.eps_folder_path = "\\\\192.0.2.2\\Music\\Eps"
            self.music_folder_path = "\\\\192.0.2.2\\Music"
            self.delimiter = '\\'
        print('import_folder_path = ' + self.import_folder_path)
        print('music_folder_path = ' + self.eps_folder_path)
        print('delimiter = ' + self.delimiter)
        self.rescan = rescan