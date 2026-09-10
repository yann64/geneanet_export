from exportgeneanet.identifiers import PersonKey
from exportgeneanet.media_downloader import _filename_for, _force_https


def test_force_https_rewrites_plain_http():
    assert _force_https("http://example.com/photo.jpg") == "https://example.com/photo.jpg"


def test_force_https_leaves_https_unchanged():
    assert _force_https("https://example.com/photo.jpg") == "https://example.com/photo.jpg"


def test_filename_for_uses_person_key_and_index_not_remote_name():
    key = PersonKey(p="jean", n="dupont", oc=0)
    name = _filename_for(key, 0, "https://example.com/some/remote/name.jpg")
    assert name == "jean.dupont.0-0.jpg"


def test_filename_for_falls_back_to_default_extension_when_theres_no_suffix():
    key = PersonKey(p="jean", n="dupont", oc=0)
    assert _filename_for(key, 0, "https://example.com/photo").endswith(".jpg")
    # A trailing "../../etc/passwd"-style path component has no dot-suffix
    # at all (Path.suffix looks only at the final component) — falls back
    # to the default extension rather than propagating anything odd.
    assert _filename_for(key, 0, "https://example.com/photo.jpg/../../etc/passwd").endswith(".jpg")


def test_filename_for_never_uses_the_remote_path_itself():
    key = PersonKey(p="jean", n="dupont", oc=0)
    name = _filename_for(key, 0, "https://example.com/../../etc/passwd.jpg")
    assert name == "jean.dupont.0-0.jpg"
    assert "/" not in name and ".." not in name


def test_filename_for_keeps_a_safe_known_extension():
    key = PersonKey(p="jean", n="dupont", oc=0)
    assert _filename_for(key, 2, "https://example.com/a/b.png").endswith(".png")
