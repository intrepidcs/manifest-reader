from manifest_reader.vivado_util import update_ip
import tempfile
from pathlib import Path

def main():
    cwd = Path.cwd()
    update_ip(cwd)

if __name__ == "__main__":
    main()