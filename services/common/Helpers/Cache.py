from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.common.Helpers.LookupTableHelper import LookupTableHelper
from services.common.Helpers.TableHelper import TableHelper

databaseHelpers = {'artists': TableHelper('artists', 'name'),
                   'ignored_artists': FilterTableHelper('ignored_artists', 'name', 'corrected_name'),
                   'genres': FilterTableHelper('genres', 'genre', 'corrected_genre'),
                   'ignored_genres': FilterTableHelper('ignored_genres', 'name', 'corrected_name'),
                   'artistGenreHelper': LookupTableHelper('artist_genre', 'artist', 'genre'),
                   'labelGenreHelper': LookupTableHelper('label_genre', 'label', 'genre'),
                   'subgenreHelper': LookupTableHelper('subgenre_genre', 'subgenre', 'genre')}
