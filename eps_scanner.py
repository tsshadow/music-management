#musicFolderPath = "\\\\192.0.2.2\\Music\\Eps"
musicFolderPath = "\\volume1\\Music\\Eps"

from os import listdir
from os.path import isfile, join


def scan():
    totalcount = 0;
    onlyfolders = [f for f in listdir(musicFolderPath) if not isfile(join(musicFolderPath, f))]
    for folder in onlyfolders:
        if not '__' in folder:
            subfolder = [fi for fi in listdir(musicFolderPath+'\\'+folder) if not isfile(join(musicFolderPath+'\\'+folder, fi))]
            print(folder +', '+ str(len(subfolder)))
            totalcount = totalcount + len(subfolder)
    print('labels: '+str(len(onlyfolders)))
    print('eps: '+str(totalcount))
