import logging


class LookupTableHelper:

    def __init__(self, file_path):
        self.map = self.load_map_from_file(file_path)

    @staticmethod
    def load_map_from_file(file_path):
        local_map = {}

        with open(file_path, 'r') as file:
            for line in file:
                key, values = line.strip().split(':')
                local_map[key] = values.split(',')
        return local_map

    def get(self, key):
        return self.map.get(key)
