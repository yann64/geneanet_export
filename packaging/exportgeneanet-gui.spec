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

# PySide6's Linux wheel vendors its own copy of glib/gio/gobject — usually
# older than the host's. A frozen onefile app extracts to a temp dir and
# puts it first on the library search path, so if anything later dlopen()s
# a *system* GIO module (confirmed real: GVFS's D-Bus module, loaded simply
# by running the app on a real desktop — never triggered by this project's
# earlier offscreen-only testing), that module resolves symbols against the
# bundled, older glib instead of the system glib it was actually built
# against. Real symptom hit on a real user's machine: the bundled glib is
# missing `g_variant_builder_init_static` (added in GLib 2.70), so loading
# /usr/lib/x86_64-linux-gnu/gio/modules/libgvfsdbus.so segfaults the whole
# process. Fix: don't bundle these at all — glib guarantees strict ABI
# backward compatibility, and it's a near-universal base dependency on any
# Linux desktop, so falling back to the system's own copy (which is what a
# normal, non-frozen Qt app already links against) is safe.
_EXCLUDED_LIB_PREFIXES = (
    "libglib-2.0",
    "libgio-2.0",
    "libgobject-2.0",
    "libgmodule-2.0",
    "libgthread-2.0",
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
