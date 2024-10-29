import sys
from time import sleep

from processing.extractor import Extractor
from processing.mover import Mover
from processing.renamer import Renamer
from data.settings import Settings
# from data.database import Database
# from postprocessing.scanner import Scanner
from postprocessing.tagger import Tagger

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Run command with \'main.py docker\' or \'main.py windows\'')
    else:
        settings = Settings()

        if len(sys.argv) < 3:
            settings.initialize(sys.argv[1], "")
        else:
            settings.initialize(sys.argv[1], sys.argv[2])


        tagger = Tagger()
        # extractor = Extractor()
        # renamer = Renamer()
        # mover = Mover()
        # database = Database()
        # scanner = scanner.Scanner(database)

        # while True:
        tagger.tag()
        # extractor.extract()
        # renamer.rename()
        # mover.move()

        print('sleeping for 300s')
        sleep(300)
