import os
import shutil

BASE_DIR = "/volume1/Music/Youtube"

def fix_nested_youtube_dirs():
    for uploader in os.listdir(BASE_DIR):
        uploader_path = os.path.join(BASE_DIR, uploader)
        print(f"Checking uploader folder: {uploader_path}")
        if not os.path.isdir(uploader_path):
            continue

        for subdir in os.listdir(uploader_path):
            nested_path = os.path.join(uploader_path, subdir)
            if os.path.isdir(nested_path):
                # Check if it wrongly contains another uploader folder
                deeper_uploader = os.path.join(nested_path, uploader)
                if os.path.isdir(deeper_uploader):
                    print(f"Fixing: {deeper_uploader}")
                    for file in os.listdir(deeper_uploader):
                        src = os.path.join(deeper_uploader, file)
                        dst = os.path.join(uploader_path, file)

                        if not os.path.exists(dst):
                            shutil.move(src, dst)
                        else:
                            print(f"Skipped existing file: {dst}")

                    # Remove empty dirs
                    shutil.rmtree(nested_path, ignore_errors=True)

if __name__ == "__main__":
    fix_nested_youtube_dirs()
