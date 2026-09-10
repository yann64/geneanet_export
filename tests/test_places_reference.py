from exportgeneanet.places_reference import resolve


def test_resolve_matches_real_four_segment_place():
    chain = resolve("Sérignan, Hérault, Occitanie, France")
    assert [p.type for p in chain] == ["Country", "Region", "Department", "City"]
    assert [p.name for p in chain] == ["France", "Occitanie", "Hérault", "Sérignan"]
    assert chain[-1].id == "P24214"


def test_resolve_drops_postcode_segment():
    with_postcode = resolve("Maraussan, 34370, Hérault, Languedoc-Roussillon, FRANCE")
    without_postcode = resolve("Maraussan, Hérault, Languedoc-Roussillon, France")
    assert with_postcode == without_postcode
    assert with_postcode[-1].name == "Maraussan"


def test_resolve_country_casing_is_normalized():
    assert resolve("Maraussan, Hérault, Occitanie, FRANCE") == resolve(
        "Maraussan, Hérault, Occitanie, France"
    )


def test_resolve_disambiguates_duplicate_city_names_by_department():
    # "Selles" names 4 different real communes in 4 different departments —
    # matching must not conflate them.
    marne = resolve("Selles, Marne, Grand Est, France")
    eure = resolve("Selles, Eure, Normandie, France")
    assert marne[-1].handle != eure[-1].handle
    assert marne[-2].name == "Marne"
    assert eure[-2].name == "Eure"


def test_resolve_strips_locality_prefix_from_city_segment():
    chain = resolve("Campmarcel - Puivert, Aude, Languedoc-Roussillon, FRANCE")
    assert chain[-1].name == "Puivert"


def test_resolve_falls_back_to_country_only_for_foreign_city():
    chain = resolve("Muscat, Oman")
    assert [p.type for p in chain] == ["Country"]
    assert chain[0].name == "Oman"


def test_resolve_returns_empty_for_no_match_at_all():
    assert resolve("Nowhereville, Nonexistentia") == []


def test_resolve_returns_empty_for_missing_text():
    assert resolve(None) == []
    assert resolve("") == []
