# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements

# --- Desktop entry -----------------------------------------------------------
desktop_file = i18n.merge_file(
        input: '@0@.desktop.in'.format(application_id),
       output: '@0@.desktop'.format(application_id),
         type: 'desktop',
       po_dir: '../po',
      install: true,
  install_dir: datadir / 'applications',
)

desktop_utils = find_program('desktop-file-validate', required: false)
if desktop_utils.found()
  test('Validate desktop file', desktop_utils, args: [desktop_file])
endif

# --- AppStream metainfo ------------------------------------------------------
metainfo_file = i18n.merge_file(
        input: '@0@.metainfo.xml.in'.format(application_id),
       output: '@0@.metainfo.xml'.format(application_id),
         type: 'xml',
       po_dir: '../po',
      install: true,
  install_dir: datadir / 'metainfo',
)

appstream_util = find_program('appstreamcli', required: false)
if appstream_util.found()
  test('Validate metainfo', appstream_util,
       args: ['validate', '--no-net', '--explain', metainfo_file])
endif

# --- GSettings schema --------------------------------------------------------
install_data(
  '@0@.gschema.xml'.format(application_id),
  install_dir: datadir / 'glib-2.0' / 'schemas',
)

compile_schemas = find_program('glib-compile-schemas', required: false)
if compile_schemas.found()
  test('Validate schema', compile_schemas,
       args: ['--strict', '--dry-run', meson.current_source_dir()])
endif

# --- Blueprint UI ------------------------------------------------------------
# Compile .blp sources to .ui in the build tree, preserving the ui/ subpath so
# the GResource can reference them as "ui/<name>.ui".
blueprint_compiler = find_program('blueprint-compiler')

blueprints = custom_target('blueprints',
  input: files(
    'ui/window.blp',
    'ui/preferences.blp',
  ),
  output: '.',
  command: [
    blueprint_compiler, 'batch-compile',
    '@OUTPUT@', '@CURRENT_SOURCE_DIR@', '@INPUT@',
  ],
)

# --- GResource (UI etc.) -----------------------------------------------------
gnome.compile_resources(
  application_id,
  '@0@.gresource.xml'.format(application_id),
  gresource_bundle: true,
  dependencies: blueprints,
  install: true,
  install_dir: pkgdatadir,
)

subdir('icons')
