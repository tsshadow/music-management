import sys

from data.settings import Settings
from postprocessing.retagger import ReTagger
from processing.mover import Mover
from processing.extractor import Extractor
from processing.renamer import Renamer

# from analyzing import database, scanner


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Run command with \'main.py docker\' or \'main.py windows\'')
    else:
        settings = Settings()
        settings.initialize(sys.argv[1])

        extractor = Extractor()
        renamer = Renamer()
        mover = Mover()
        reTagger = ReTagger()
        # database = database.Database()
        # scanner = scanner.Scanner(database)

        # counter = 75
        while True:
            # extractor.extract()
            # renamer.rename()
            # mover.move()
            reTagger.ReTag()

            # if counter > 72:
            #     counter = 0
            #     scanner.scan()
            # counter = counter + 1
            # print('sleeping for 300s')
            # sleep(300)
