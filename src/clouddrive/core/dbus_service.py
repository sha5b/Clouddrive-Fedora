# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""D-Bus status service consumed by the host Nautilus extension.

The sandboxed UI publishes per-path sync status (and accepts commands like
"sync this folder" / "free up space") on the session bus. The Nautilus
extension (host side) calls this to draw emblems and menu items.

Stage 0: interface name + method outline. Implemented in stage 4 alongside the
Nautilus extension.
"""

BUS_NAME = "com.fiberelements.Clouddrive"
OBJECT_PATH = "/com/fiberelements/Clouddrive/Sync"
INTERFACE = "com.fiberelements.Clouddrive.Sync"

# Introspection XML the service will export (stage 4):
INTROSPECTION_XML = """
<node>
  <interface name="com.fiberelements.Clouddrive.Sync">
    <!-- Returns a status enum string for a local path. -->
    <method name="StatusForPath">
      <arg type="s" name="path" direction="in"/>
      <arg type="s" name="status" direction="out"/>
    </method>
    <method name="SyncPath">
      <arg type="s" name="path" direction="in"/>
    </method>
    <method name="FreeUpSpace">
      <arg type="s" name="path" direction="in"/>
    </method>
    <method name="CreateShareLink">
      <arg type="s" name="path" direction="in"/>
      <arg type="b" name="editable" direction="in"/>
      <arg type="s" name="url" direction="out"/>
    </method>
    <!-- Emitted when a path's status changes so the extension can refresh. -->
    <signal name="StatusChanged">
      <arg type="s" name="path"/>
      <arg type="s" name="status"/>
    </signal>
  </interface>
</node>
"""


class SyncStatusService:
    """Stage 4: own the bus name and dispatch the methods above."""

    def __init__(self, connection=None):
        self._connection = connection

    def publish(self) -> None:
        raise NotImplementedError("D-Bus service lands in stage 4")
