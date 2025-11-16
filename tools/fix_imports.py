from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]  # repo root

MODULE_MAP = {
    # ---------- postprocessing.* ----------

    # constants / top-level
    "postprocessing.constants": "services.tagger.constants",
    "postprocessing.tagger": "services.tagger.tagger",
    "postprocessing.analyze": "services.analyzer_service.analyzer",  # evt. handmatig checken
    "postprocessing.analyzer": "services.analyzer_service.analyzer",
    "postprocessing.sanitizer": "services.other.sanitizer",
    "postprocessing.artistfixer": "services.other.artistfixer",
    "postprocessing.repair": "services.other.repair",
    "postprocessing": "services.tagger_service",  # 1 gebruik; even checken of dit klopt

    # Helpers -> services/common/Helpers/*
    "postprocessing.Song.Helpers.DatabaseConnector": "services.common.Helpers.DatabaseConnector",
    "postprocessing.Song.Helpers.TableHelper": "services.common.Helpers.TableHelper",
    "postprocessing.Song.Helpers.FilterTableHelper": "services.common.Helpers.FilterTableHelper",
    "postprocessing.Song.Helpers.LookupTableHelper": "services.common.Helpers.LookupTableHelper",
    "postprocessing.Song.Helpers.Cache": "services.common.Helpers.Cache",
    "postprocessing.Song.Helpers.FestivalHelper": "services.common.Helpers.FestivalHelper",
    "postprocessing.Song.Helpers.BrokenSongHelper": "services.common.Helpers.BrokenSongHelper",
    "postprocessing.Song.Helpers.BrokenSongArtistLookupHelper": "services.common.Helpers.BrokenSongArtistLookupHelper",

    # Song classes -> services/tagger/Song/*
    "postprocessing.Song.BaseSong": "services.tagger.Song.BaseSong",
    "postprocessing.Song.Tag": "services.tagger.Song.Tag",
    "postprocessing.Song.SoundcloudSong": "services.tagger.Song.SoundcloudSong",
    "postprocessing.Song.YoutubeSong": "services.tagger.Song.YoutubeSong",
    "postprocessing.Song.LabelSong": "services.tagger.Song.LabelSong",
    "postprocessing.Song.GenericSong": "services.tagger.Song.GenericSong",
    "postprocessing.Song.TelegramSong": "services.tagger.Song.TelegramSong",
    "postprocessing.Song.TagCollection": "services.tagger.Song.TagCollection",

    # rules -> services/tagger/Song/rules/*
    "postprocessing.Song.rules.TagRule": "services.tagger.Song.rules.TagRule",
    "postprocessing.Song.rules.CleanAndFilterGenreRule": "services.tagger.Song.rules.CleanAndFilterGenreRule",
    "postprocessing.Song.rules.CleanTagsRule": "services.tagger.Song.rules.CleanTagsRule",
    "postprocessing.Song.rules.InferGenreFromArtistRule": "services.tagger.Song.rules.InferGenreFromArtistRule",
    "postprocessing.Song.rules.InferGenreFromSubgenreRule": "services.tagger.Song.rules.InferGenreFromSubgenreRule",
    "postprocessing.Song.rules.ReplaceInvalidUnicodeRule": "services.tagger.Song.rules.ReplaceInvalidUnicodeRule",
    "postprocessing.Song.rules.AddMissingArtistToDatabaseRule": "services.tagger.Song.rules.AddMissingArtistToDatabaseRule",
    "postprocessing.Song.rules.CheckArtistRule": "services.tagger.Song.rules.CheckArtistRule",
    "postprocessing.Song.rules.TagResult": "services.tagger.Song.rules.TagResult",
    "postprocessing.Song.rules.AddMissingGenreToDatabaseRule": "services.tagger.Song.rules.AddMissingGenreToDatabaseRule",
    "postprocessing.Song.rules.InferArtistFromTitleRule": "services.tagger.Song.rules.InferArtistFromTitleRule",
    "postprocessing.Song.rules.InferFestivalFromTitleRule": "services.tagger.Song.rules.InferFestivalFromTitleRule",
    "postprocessing.Song.rules.InferGenreFromAlbumArtistRule": "services.tagger.Song.rules.InferGenreFromAlbumArtistRule",
    "postprocessing.Song.rules.AnalyzeBpmRule": "services.tagger.Song.rules.AnalyzeBpmRule",
    "postprocessing.Song.rules.VerifyArtistRule": "services.tagger.Song.rules.VerifyArtistRule",
    "postprocessing.Song.rules.NormalizeFlacTagsRule": "services.tagger.Song.rules.NormalizeFlacTagsRule",
    "postprocessing.Song.rules.InferGenreFromTitleRule": "services.tagger.Song.rules.InferGenreFromTitleRule",
    "postprocessing.Song.rules.InferGenreFromLabelRule": "services.tagger.Song.rules.InferGenreFromLabelRule",
    "postprocessing.Song.rules.MergeDrumAndBassGenresRule": "services.tagger.Song.rules.MergeDrumAndBassGenresRule",
    "postprocessing.Song.rules.ExternalArtistLookup": "services.tagger.Song.rules.ExternalArtistLookup",
    "postprocessing.Song.rules.InferRemixerFromTitleRule": "services.tagger.Song.rules.InferRemixerFromTitleRule",

    # ---------- processing.* ----------

    # importer
    "processing.extractor": "services.importer_service.extractor",
    "processing.mover": "services.importer_service.mover",
    "processing.renamer": "services.importer_service.renamer",

    # other-service
    "processing.converter": "services.other.converter",
    "processing.epsflattener": "services.other.epsflattener",

    # ---------- analyzer.* ----------

    # db / matching
    "analyzer.db.repo": "services.analyzer_service.analyzer.db.repo",
    "analyzer.matching.uid": "services.analyzer_service.analyzer.matching.uid",
    "analyzer.matching.normalizer": "services.analyzer_service.analyzer.matching.normalizer",

    # services
    "analyzer.services.library_admin_service": "services.analyzer_service.analyzer.services.library_admin_service",
    "analyzer.services.library_stats_service": "services.analyzer_service.analyzer.services.library_stats_service",
    "analyzer.services.summary_service": "services.analyzer_service.analyzer.services.summary_service",
    "analyzer.services.library_service": "services.analyzer_service.analyzer.services.library_service",
    "analyzer.services.match_service": "services.analyzer_service.analyzer.services.match_service",
    "analyzer.services.enrich_service": "services.analyzer_service.analyzer.services.enrich_service",

    # api / jobs / ingestion
    "analyzer.api.router": "services.analyzer_service.analyzer.api.router",
    "analyzer.jobs.queue": "services.analyzer_service.analyzer.jobs.queue",
    "analyzer.ingestion.filesystem": "services.analyzer_service.analyzer.ingestion.filesystem",
}


class ImportRewriter(ast.NodeTransformer):
    def __init__(self, module_map: dict[str, str]):
        # alleen mappings met een niet-lege value
        self.module_map = {k: v for k, v in module_map.items() if v}

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module in self.module_map:
            node.module = self.module_map[node.module]
        return self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name in self.module_map:
                alias.name = self.module_map[alias.name]
        return self.generic_visit(node)


def fix_file(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return

    new_tree = ImportRewriter(MODULE_MAP).visit(tree)
    ast.fix_missing_locations(new_tree)

    new_src = ast.unparse(new_tree)  # Python 3.9+

    if new_src != src:
        path.write_text(new_src, encoding="utf-8")
        print(f"Updated: {path}")


def main():
    for py in ROOT.rglob("*.py"):
        if ".venv" in py.parts or "__pycache__" in py.parts or "tools" in py.parts:
            continue
        fix_file(py)


if __name__ == "__main__":
    main()
