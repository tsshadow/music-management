import mutagen
print(f"mutagen file: {mutagen.__file__}")
try:
    print(f"mutagen path: {mutagen.__path__}")
except AttributeError:
    print("mutagen has no __path__")
import mutagen.easyid3
print("Import successful")
