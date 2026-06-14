# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei

scalable_dir = 'hicolor' / 'scalable' / 'apps'
install_data(
  scalable_dir / '@0@.svg'.format(application_id),
  install_dir: datadir / 'icons' / scalable_dir,
)

symbolic_dir = 'hicolor' / 'symbolic' / 'apps'
install_data(
  symbolic_dir / '@0@-symbolic.svg'.format(application_id),
  install_dir: datadir / 'icons' / symbolic_dir,
)

# Raster sizes for environments that prefer PNGs (taskbars, some shells, and
# Flathub's icon validation). Rendered from the scalable SVG.
foreach size : ['48', '64', '128', '256', '512']
  png_dir = 'hicolor' / '@0@x@0@'.format(size) / 'apps'
  install_data(
    png_dir / '@0@.png'.format(application_id),
    install_dir: datadir / 'icons' / png_dir,
  )
endforeach
