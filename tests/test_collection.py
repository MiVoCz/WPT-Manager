from uuid import UUID

import pytest

from wpt_manager.models.collection import Collection


def test_collection_defaults():
    collection = Collection(name="Výlet do Francie")

    assert isinstance(collection.id, UUID)
    assert collection.name == "Výlet do Francie"
    assert collection.description == ""
    assert collection.source == ""
    assert collection.source_file == ""


def test_collection_name_is_required():
    with pytest.raises(TypeError):
        Collection()


def test_collection_custom_values():
    collection = Collection(
        name="Výlet do Francie",
        description="Zajímavá místa ve Francii.",
        source="Mapy.com",
        source_file="francie.gpx",
    )

    assert collection.name == "Výlet do Francie"
    assert collection.description == "Zajímavá místa ve Francii."
    assert collection.source == "Mapy.com"
    assert collection.source_file == "francie.gpx"
