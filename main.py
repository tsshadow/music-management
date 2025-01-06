import sys
from time import sleep

from processing.extractor import Extractor
from processing.mover import Mover
from processing.renamer import Renamer
from data.settings import Settings
from postprocessing.tagger import Tagger

if __name__ == '__main__':
    settings = Settings()

    tagger = Tagger()
    extractor = Extractor()
    renamer = Renamer()
    mover = Mover()

    while True:
        extractor.extract()
        renamer.rename()
        mover.move()
        tagger.tag()
        sleep(4*3600)
