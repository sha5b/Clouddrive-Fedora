# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements

moduledir = pkgdatadir / 'clouddrive'

# Configured launcher script installed as `clouddrive` on PATH.
conf = configuration_data()
conf.set('PYTHON', python.full_path())
conf.set('VERSION', meson.project_version())
conf.set('APP_ID', application_id)
conf.set('localedir', localedir)
conf.set('pkgdatadir', pkgdatadir)

configure_file(
         input: 'clouddrive.in',
        output: 'clouddrive',
  configuration: conf,
       install: true,
   install_dir: bindir,
  install_mode: 'rwxr-xr-x',
)

# Install the Python package next to the GResource bundle.
install_subdir('clouddrive', install_dir: pkgdatadir)
