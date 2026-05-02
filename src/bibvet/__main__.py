"""Allow `python -m bibvet`."""
import sys

from bibvet.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
