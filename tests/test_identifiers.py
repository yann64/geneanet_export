import pytest

from exportgeneanet.identifiers import PersonKey


def test_person_key_str_roundtrip():
    key = PersonKey(p="jean", n="dupont", oc=2)
    assert str(key) == "jean.dupont.2"
    assert PersonKey.parse(str(key)) == key


def test_person_key_parse_defaults_oc_to_zero():
    assert PersonKey.parse("jean.dupont") == PersonKey(p="jean", n="dupont", oc=0)


def test_person_key_parse_rejects_missing_surname():
    with pytest.raises(ValueError):
        PersonKey.parse("jean")
