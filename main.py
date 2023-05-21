import eps_mover

import eps_renamer
import eps_scanner

if __name__ == '__main__':
    eps_renamer.rename()
    eps_mover.move()
    eps_scanner.scan()

