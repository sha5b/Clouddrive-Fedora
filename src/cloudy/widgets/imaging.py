# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei
"""Shared image decoding for the inline-image surfaces (mail/chat/teams/editor)."""

from __future__ import annotations


def thumbnail_texture(data: bytes, max_edge: int):
    """Decode image bytes into a ``Gdk.Texture`` downscaled so its longest side
    is at most ``max_edge`` px.

    The downscale happens *during* decode (the loader's ``size-prepared``
    signal), so a huge source image (a OneNote scan, a high-res screenshot) is
    never fully decoded into memory — keeping the GPU upload under the texture
    limit and stopping an over-large image from OOM-ing the renderer. Raises
    ``ValueError`` if the bytes can't be decoded."""
    from gi.repository import Gdk, GdkPixbuf

    loader = GdkPixbuf.PixbufLoader()

    def _on_size(ldr, w, h):
        if w <= 0 or h <= 0:
            return
        scale = min(1.0, max_edge / w, max_edge / h)
        if scale < 1.0:
            ldr.set_size(max(1, int(w * scale)), max(1, int(h * scale)))

    loader.connect("size-prepared", _on_size)
    loader.write(data)
    loader.close()
    pix = loader.get_pixbuf()
    if pix is None:
        raise ValueError("undecodable image")
    return Gdk.Texture.new_for_pixbuf(pix)
