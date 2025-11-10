from postprocessing.tagger import Tagger


def run_tagger(steps):
    """Run the tagger with the appropriate parsing options."""
    parse_all = "tag" in steps
    tagger = Tagger()
    tagger.run(
        parse_labels=parse_all or "tag-labels" in steps,
        parse_soundcloud=parse_all or "tag-soundcloud" in steps,
        parse_youtube=parse_all or "tag-youtube" in steps,
        parse_generic=parse_all or "tag-generic" in steps,
        parse_telegram=parse_all or "tag-telegram" in steps,
    )
