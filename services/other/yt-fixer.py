import os
import shutil
BASE_DIR = '/volume1/Music/Youtube'

def fix_nested_youtube_dirs():
    for uploader in os.listdir(BASE_DIR):
        uploader_path = os.path.join(BASE_DIR, uploader)
        print(f'Checking uploader folder: {uploader_path}')
        if not os.path.isdir(uploader_path):
            continue
        _process_uploader_subdirs(uploader, uploader_path)

def _process_uploader_subdirs(uploader, uploader_path):
    for subdir in os.listdir(uploader_path):
        nested_path = os.path.join(uploader_path, subdir)
        if not os.path.isdir(nested_path):
            continue
        deeper_uploader = os.path.join(nested_path, uploader)
        if os.path.isdir(deeper_uploader):
            _move_files_and_cleanup(deeper_uploader, uploader_path, nested_path)

def _move_files_and_cleanup(src_dir, dst_root, dir_to_remove):
    print(f'Fixing: {src_dir}')
    for file in os.listdir(src_dir):
        src = os.path.join(src_dir, file)
        dst = os.path.join(dst_root, file)
        if not os.path.exists(dst):
            shutil.move(src, dst)
        else:
            print(f'Skipped existing file: {dst}')
    shutil.rmtree(dir_to_remove, ignore_errors=True)
if __name__ == '__main__':
    fix_nested_youtube_dirs()
