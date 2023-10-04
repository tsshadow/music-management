import sys
from time import sleep

import config
import renamer
import mover
import scanner
import extractor
import database

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Run command with \'main.py docker\' or \'main.py windows\'')
    else:
        settings = config.Settings()
        settings.initialize(sys.argv[1])

        extractor = extractor.Extractor()
        renamer = renamer.Renamer()
        mover = mover.Mover()
        database = database.Database()
        scanner = scanner.Scanner(database)

        counter = 75;
        while True:
            extractor.extract()
            renamer.rename()
            mover.move()

            if (counter > 72):
                counter = 0
                scanner.scan()
            counter = counter + 1;
            print('sleeping for 300s')
            sleep(300)
