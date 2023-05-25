import sys
from time import sleep

import config
import renamer
import mover
import scanner

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Run command with \'main.py docker\' or \'main.py windows\'')
    else:
        settings = config.Settings()
        settings.initialize(sys.argv[1])

        renamer = renamer.Renamer()
        mover = mover.Mover()
        scanner = scanner.Scanner()
        while True:
            renamer.rename()
            mover.move()
            scanner.scan()

            print('sleeping for 1 hour')
            sleep(3600)
