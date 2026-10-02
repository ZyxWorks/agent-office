#!/bin/sh
# Agent Office 1.0's installer: the same as `office install`. Shows every change first.
# The tmux office (0.x) installer is bin/install-tmux.
exec "$(dirname "$0")/bin/office" install "$@"
