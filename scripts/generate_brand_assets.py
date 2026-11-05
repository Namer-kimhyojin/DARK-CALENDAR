# -*- coding: utf-8 -*-
"""Compatibility entrypoint for the current feather icon generation pipeline."""

if __package__:
    from scripts.generate_icons import main
else:
    from generate_icons import main


if __name__ == "__main__":
    main()
