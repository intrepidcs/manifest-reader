# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2020, Lars Asplund lars.anders.asplund@gmail.com

from pathlib import Path
from shutil import rmtree
from vunit.vivado import run_vivado


def main():
    root = Path(__file__).parent.resolve()
    project_name = "myproject"
    generate_vivado_project(prj, project_name)


def generate_vivado_project(folder, project_name, clean=True):
    print(f"Creating project {project_name} at {folder}")
    prj = folder / project_name
    root = Path(__file__).parent.resolve()
    run_vivado(root / "tcl" / "generate_project.tcl", tcl_args=[folder, project_name])


if __name__ == "__main__":
    main()
