# musicFolderPath = "\\\\192.0.2.2\\Music\\Eps"
musicFolderPath = "/music"

from os import listdir
from os.path import isfile, join


def scan():
    total_count = 0;
    only_folders = [f for f in listdir(musicFolderPath) if not isfile(join(musicFolderPath, f))]
    for folder in only_folders:
        if not '__' in folder:
            sub_folder = [fi for fi in listdir(musicFolderPath + '\\' + folder) if
                          not isfile(join(musicFolderPath + '\\' + folder, fi))]
            print(folder + ', ' + str(len(sub_folder)))
            total_count = total_count + len(sub_folder)
    print('labels: ' + str(len(only_folders)))
    print('eps: ' + str(total_count))
