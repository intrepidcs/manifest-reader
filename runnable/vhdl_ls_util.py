#!/usr/bin/env python
#
# Copyright (c) 2022, Intrepid Control Systems, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Copyright 2021 Intrepid Control Systems
Author: Nathan Francque

Utility for interacting with VHDL LS using our manifest files

"""
from pathlib import Path
import sys
from os import environ
from pprint import pprint
import toml
import re

# Add the repo to our path manually for runnables
# This way startfile not required
SCRIPT_DIR = Path(__file__).parent
UTILS_DIR = SCRIPT_DIR / ".."
sys.path.append(str(UTILS_DIR.resolve()))

import blocks_reader
import manifest_reader

args = sys.argv
assert len(args) >= 2, "expected at least 1 argument for the base directory!"
BASE_DIR = Path(args[1])
DIRS = args[1:]
# print(DIRS)


def main():
    """
    Main function to be called on the command line
    Gets all the files in the project and outputs them into a vhdl ls toml file

    """
    libs = {}
    for p in DIRS:
        path = Path(p)
        l = get_vhdl_ls_libs(path)
        libs.update(l)

    vhdl_ls_dict = to_vhdl_ls_dict(libs)
    # pprint(vhdl_ls_dict)
    with open(BASE_DIR / "vhdl_ls.toml", "w+") as file:
        toml_str = toml.dumps(vhdl_ls_dict)
        toml_str = re.sub(r"(?<!\\)\\(?![\\])", "\\\\\\\\", toml_str)
        file.write(toml_str)


def get_vhdl_ls_libs(root_dir):
    """
    Gets libraries that vhdl ls needs as a dictionary of lists

    Args:
        root_dir: The root of the project, directory where the blocks specification exists

    Returns:
        A dictionary of lists, ret["lib_name"] is a list of file paths

    """
    blk_dirs = blocks_reader.read_blocks(root_dir)
    libs = {}
    for blk_dir in blk_dirs:
        manifest = manifest_reader.read_manifest(blk_dir)
        for file_list in manifest.file_lists:
            lib = file_list.get_lib_name(manifest.name)
            libs[lib] = []
            # Allow empty entries, just skip
            if file_list.files is None:
                continue
            for file in file_list.files:
                file = Path(file)
                full_file_path = manifest.get_source_dir(file_list.kind) / file
                libs[lib].append(str(full_file_path.resolve()))

    libs.update(get_vunit_stuff())
    return libs


def get_vunit_stuff():
    """
    Gets all vunit libs if applicable

    Returns:
        A dictionary of lists representing all vunit related libraries

    """
    try:
        import vunit

        vunit_install_dir = Path(vunit.__file__).parent
    except:
        # Vunit must not be installed, empty
        return {}
    vunit_vhdl = vunit_install_dir / "vhdl"
    ret = {}
    ret["vunit_lib"] = []
    ret["osvvm"] = []
    for file in vunit_vhdl.rglob("*.vhd"):
        if "osvvm" in str(file):
            lib = "osvvm"
        else:
            lib = "vunit_lib"
        ret[lib].append(str(file.resolve()))
    return ret


def to_vhdl_ls_dict(libs):
    """
    Converts the raw dictionary into the vhdl ls specification

    Args:
        libs: A dictionary of lists representing the libraries and files

    Returns:
        A dictionary that can be output using toml that will then be readable by vhdl ls

    """
    ret = {}
    ret["libraries"] = {}
    for lib, files in libs.items():
        ret["libraries"][lib] = {}
        ret["libraries"][lib]["files"] = files
    return ret


if __name__ == "__main__":
    main()
