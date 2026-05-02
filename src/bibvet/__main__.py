"""Allow `python -m bibvet`."""
from bibvet.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
