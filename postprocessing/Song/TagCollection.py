from postprocessing.Song.Tag import Tag


class TagCollection:
    def __init__(self, tags):
        self.tags: dict[str, Tag] = {}
        for tag in tags:
            self.tags[tag] = Tag(tag, tags[tag])
        pass

    def add(self, mp3tag, value):
        if value is not None:
            self.tags[mp3tag] = Tag(mp3tag, value)
        else:
            print("Error adding tag(" + mp3tag + "), value is none")

    def print(self):
        for tag in self.tags.values():
            tag.print()

    def has_item(self, tag):
        return tag in self.tags

    def get_item(self, tag):
        return self.tags[tag]

    def get_item_as_string(self, tag):
        try:
            return self.tags[tag].to_string()
        except:
            return ""

    def get_item_as_array(self, tag):
        try:
            return self.tags[tag].to_array()
        except:
            return []

    def get(self):
        return self.tags
