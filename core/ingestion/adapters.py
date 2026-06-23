from core.ingestion.artic import (
    ArticIngestionError,
    fetch_artic_source_items,
    is_artic_source,
)
from core.ingestion.gutendex import (
    GutendexIngestionError,
    fetch_gutendex_source_items,
    is_gutendex_source,
)
from core.ingestion.loc import LOCIngestionError, fetch_loc_source_items, is_loc_source
from core.ingestion.met import (
    MetIngestionError,
    fetch_met_source_items,
    is_met_source,
)
from core.ingestion.nasa import (
    NASAIngestionError,
    fetch_nasa_source_items,
    is_nasa_images_source,
)
from core.ingestion.wikimedia import (
    WikimediaIngestionError,
    fetch_wikimedia_source_items,
    is_wikimedia_commons_source,
)


SUPPORTED_SOURCE_TYPES = (
    "Wikimedia Commons, NASA Images, Gutendex / Project Gutenberg, "
    "The Met Open Access, Art Institute Chicago, and Library of Congress sources"
)


class SourceIngestionError(Exception):
    pass


def supports_source_discovery(source):
    return (
        is_wikimedia_commons_source(source)
        or is_nasa_images_source(source)
        or is_gutendex_source(source)
        or is_met_source(source)
        or is_artic_source(source)
        or is_loc_source(source)
    )


def fetch_source_items(source, limit=10):
    try:
        if is_wikimedia_commons_source(source):
            return fetch_wikimedia_source_items(source, limit=limit)
        if is_nasa_images_source(source):
            return fetch_nasa_source_items(source, limit=limit)
        if is_gutendex_source(source):
            return fetch_gutendex_source_items(source, limit=limit)
        if is_met_source(source):
            return fetch_met_source_items(source, limit=limit)
        if is_artic_source(source):
            return fetch_artic_source_items(source, limit=limit)
        if is_loc_source(source):
            return fetch_loc_source_items(source, limit=limit)
    except (
        ArticIngestionError,
        LOCIngestionError,
        WikimediaIngestionError,
        NASAIngestionError,
        GutendexIngestionError,
        MetIngestionError,
    ) as exc:
        raise SourceIngestionError(str(exc)) from exc

    raise SourceIngestionError(
        f"Discovery is currently available for {SUPPORTED_SOURCE_TYPES} only."
    )
