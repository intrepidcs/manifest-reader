from manifest_reader.vivado_util import update_ip
import tempfile
from pathlib import Path

def main():
    cwd = Path.cwd()
    component = cwd / "component.xml"
    if not component.exists():
        raise Exception(f"No file {component} found!")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        update_ip(cwd, tmpdir)

if __name__ == "__main__":
    main()