from time import sleep

import eps_mover
import eps_renamer
import eps_scanner

if __name__ == '__main__':
    while True:
        eps_renamer.rename()
        eps_mover.move()
        # eps_scanner.scan()

        print('sleeping for 1 hour')
        sleep(3600)

