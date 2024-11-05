class UniqueTagHandler:
    def __init__(self, name, file, ignored_file):
        self.name = name
        self.tags = []
        self.file = file
        self.ignored_file = ignored_file
        self.known_tags = self.load_known_tags()
        # self.known_ignored = self.load_known_ignored_tags()
        self.known_ignored = set()

    def load_known_tags(self):
        try:
            with open(self.file, "r", encoding="utf-8") as file:
                return {line.strip() for line in file if line.strip()}
        except FileNotFoundError:
            return set()

    def load_known_ignored_tags(self):
        try:
            with open(self.ignored_file, "r", encoding="utf-8") as file:
                return {line.strip() for line in file if line.strip()}
        except FileNotFoundError:
            return set()

    def add_non_standard_names(self, tags):
        non_standard = [
            tag for tag in tags
            if
               tag not in self.known_tags and
               tag not in self.known_ignored
        ]
        self.tags.extend(non_standard)

    def verify_and_save_tag(self):
        new_tags = set(self.tags) - self.known_tags - self.known_ignored
        with open(self.file, "a", encoding="utf-8") as file:
            with open(self.ignored_file, "a", encoding="utf-8") as ignored_file:
                for tag in sorted(new_tags):
                    file.write(f"{tag}\n")
                    self.known_tags.add(tag)

    def save(self):
        self.verify_and_save_tag()


def custom_title(s):
    # List of words to ignore (not capitalize)
    ignore_words = {"of", "and", "the", "in", "on", "for", "with", "a", "an", "but", "to"}
    words = s.split()

    # Capitalize the first word and other words unless they are in ignore_words
    return ' '.join(
        word.lower() if word.lower() in ignore_words and i != 0 else word.title()
        for i, word in enumerate(words)
    )


class TitleCaseTagChecker(UniqueTagHandler):
    def __init__(self, name, file, ignored_file):
        super().__init__(name, file, ignored_file)

    def add_non_standard_names(self, tags):
        non_standard = [
            tag for tag in tags
            if tag != custom_title(tag) and
               tag not in self.known_tags and
               tag not in self.known_ignored
        ]
        self.tags.extend(non_standard)

    def verify_and_save_tag(self):
        new_tags = set(self.tags) - self.known_tags - self.known_ignored
        with open(self.file, "a", encoding="utf-8") as file:
            with open(self.ignored_file, "a", encoding="utf-8") as ignored_file:
                for tag in sorted(new_tags):

                    if custom_title(tag) not in self.known_tags:
                        response = input(
                            f"\nIs '{tag}' correctly spelled (expected '{custom_title(tag)}')? (yes/no/title): ").strip().lower()
                        if response == "yes" or response == "y":
                            file.write(f"{tag}\n")
                            self.known_tags.add(tag)
                        elif response == "no" or response == "n":
                            ignored_file.write(f"{tag}\n")
                            self.known_ignored.add(tag)
                        elif response == "title" or response == "t":
                            file.write(f"{custom_title(tag)}\n")
                            self.known_tags.add(custom_title(tag))
                        else:
                            self.tags.remove(tag)

    def save(self):
        self.verify_and_save_tag()
