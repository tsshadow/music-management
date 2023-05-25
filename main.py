import sys
from time import sleep

import config
import renamer
import mover
import scanner
import extractor

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Run command with \'main.py docker\' or \'main.py windows\'')
    else:
        settings = config.Settings()
        settings.initialize(sys.argv[1])

        extractor = extractor.Extractor()
        renamer = renamer.Renamer()
        mover = mover.Mover()
        scanner = scanner.Scanner()
        while True:
            extractor.extract()
            renamer.rename()
            mover.move()
            scanner.scan()

            print('sleeping for 1 hour')
            sleep(3600)
