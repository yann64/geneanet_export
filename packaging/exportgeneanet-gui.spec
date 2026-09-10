# -*- mode: python ; coding: utf-8 -*-
#
# Not auto-generated boilerplate to gitignore: this file exists specifically
# to exclude a handful of bundled shared libraries (see below) — something
# plain PyInstaller CLI flags can't express. scripts/build_executable.py
# runs PyInstaller against this file.

a = Analysis(
    ["run_gui.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# PyInstaller's Linux dependency walker bundles copies of whatever
# glib/X11/xkb/D-Bus libraries happen to be installed on the *build*
# machine. Those aren't ordinary app libraries: they're the client side of
# a live protocol (X11, XKB keymaps, D-Bus) or of a plugin-loading system
# (GIO) that talks to whatever the *running* desktop actually provides —
# they need to match the target system, not the build machine, and a
# onefile build's extraction dir being first on the library search path
# means the bundled (build-machine) copy wins even though the target
# system already has its own, version-matched one. Two confirmed real
# crashes from exactly this, both never caught by this project's earlier
# offscreen-only testing (QT_QPA_PLATFORM=offscreen never touches GIO
# modules or a real X server):
#   - v0.1.0: bundled glib missing `g_variant_builder_init_static` (added
#     in GLib 2.70) crashed loading the system's GVFS D-Bus GIO module.
#   - v0.1.1 (after excluding glib): bundled libxkbcommon segfaulted
#     parsing the running X server's own keymap data (dmesg: "segfault
#     ... in libxkbcommon.so.0").
# Rather than keep finding these one crash report at a time, exclude the
# whole category: X11/xcb client libraries, xkbcommon, D-Bus, glib/gio,
# and fontconfig (same class of risk — a versioned on-disk cache format —
# though not yet linked to a crash). All are near-universal base
# dependencies of any Linux desktop capable of running a GUI app at all,
# so falling back to the system's own copies (what a normal, non-frozen
# Qt app already does) is safe — libGL.so/libEGL.so (GPU-driver-tied, the
# same risk again) aren't in this list because PyInstaller already
# excludes those by default.
_EXCLUDED_LIB_PREFIXES = (
    "libglib-2.0",
    "libgio-2.0",
    "libgobject-2.0",
    "libgmodule-2.0",
    "libgthread-2.0",
    "libX11",
    "libxcb",
    "libxkbcommon",
    "libdbus-1",
    "libfontconfig",
)
a.binaries = [b for b in a.binaries if not b[0].startswith(_EXCLUDED_LIB_PREFIXES)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="exportgeneanet-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
