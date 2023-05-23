import sys
from time import sleep

import eps_mover
import eps_renamer
import eps_scanner

# import_folder_path = "\\\\192.0.2.2\\Music\\Eps\\__TODO"
# music_folder_path = "\\\\192.0.2.2\\Music\\Eps"
music_folder_path = "/music"
import_folder_path = "/music/__TODO"

if __name__ == '__main__':
    if len(sys.argv) < 2 :
        print('Run command with \'main.py docker\' or \'main.py windows\'')
    else:
        while True:
            eps_renamer.rename(sys.argv[1])
            eps_mover.move(sys.argv[1])
            # eps_scanner.scan()

            print('sleeping for 1 hour')
            sleep(3600)

