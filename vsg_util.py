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

import manifest_reader
import blocks_reader
import yaml
from os import environ
from pathlib import Path
import argparse
import fnmatch
import re
import subprocess
import sys

THIS_DIR = Path(__file__).parent


def get_vsg_files(root_dir, exclude_patterns=None):
    """
    Gets files that should be added to the VSG run

    Args:
        root_dir: The root of the project, directory where the blocks specification exists

    Returns:
        A list of files to include in the vsg run
    """
    blk_dirs = blocks_reader.read_blocks(root_dir, local_only=True)
    vsg_files = []
    for blk_dir in blk_dirs:
        manifest = manifest_reader.read_manifest(blk_dir)
        for file_list in manifest.file_lists:
            # Allow empty entries, just skip
            if file_list.files is None:
                continue
            for file in file_list.files:
                file = Path(file)
                full_file_path = manifest.get_source_dir(file_list.kind) / file
                if exclude_patterns is not None:
                    excluded = False
                    for pattern in exclude_patterns:
                        # Convert to path and back to get the right slashes
                        pattern = str(Path(f"**/{pattern}"))
                        # Convert to regex pattern
                        pattern = re.compile(fnmatch.translate(pattern))
                        # print(pattern.pattern, full_file_path)
                        # Exclude if matches
                        if re.match(pattern, str(full_file_path)):
                            excluded = True
                            break
                    if excluded:
                        continue

                if file.suffix in [".vhd"]:
                    vsg_files.append(str(full_file_path))
    return vsg_files


def setup_vsg(root_dir, addtional_config_file=None):
    """
    Sets up vsg by gathering all the necessary files and optionally also included an existing config
    Exports the config file to scratch

    Args:
        root_dir: The root of the project, directory where the blocks specification exists
        addtional_config_file: Optional path to a vsg.yaml, if provided will be appended to default config

    Returns:
        A config file to use to run vsg
    """
    exclude_files = None
    yaml_dict = {}
    # Use default vsg config if none provided
    # For now do it this way to make getting started easier
    existing_config_path = THIS_DIR / "vsg.yaml"
    print(f"Starting with vsg config located at {existing_config_path}")
    with open(existing_config_path) as file:
        existing_config = yaml.load(file, Loader=yaml.FullLoader)

    if addtional_config_file:
        with open(addtional_config_file) as file:
            d = yaml.load(file, Loader=yaml.FullLoader)
            for k, v in d.items():
                if k in existing_config:
                    if isinstance(existing_config[k], list):
                        existing_config[k].extend(v)
                    elif isinstance(existing_config[k], dict):
                        existing_config[k].update(v)
                else:
                    existing_config[k] = v

    if "exclude" in existing_config:
        exclude_patterns = existing_config["exclude"]
    else:
        exclude_patterns = None

    yaml_dict = existing_config
    files = get_vsg_files(root_dir, exclude_patterns=exclude_patterns)
    file_list_file = root_dir / "scratch/vsg/files.yaml"
    yaml_dict.update({"file_list": files})
    # Insert existing config into the new one if provided

    if file_list_file.exists():
        file_list_file.unlink()
    if not file_list_file.parent.exists():
        file_list_file.parent.mkdir(parents=True)
    with open(file_list_file, "w") as file:
        yaml.safe_dump(yaml_dict, file)

    return file_list_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup VSG")
    print(sys.argv)
    parser.add_argument(
        "additional_config_file",
        default=None,
        nargs="?",
        help="An existing VSG config to append onto the default",
    )
    parser.add_argument(
        "--run",
        default=False,
        help="Also run vsg after setting up",
        action="store_true",
    )
    parser.add_argument(
        "--vsg-args",
        default="",
        help="Arguments to be passed to vsg run if --run specified",
    )
    args = parser.parse_args()
    config_file = setup_vsg(
        Path(environ.get("BASE_DIR", ".")), args.additional_config_file
    )
    if args.run:
        print(f"Running vsg against config {config_file}")
        # Command line might pass it in surrounded by quotes, strip out either side
        vsg_args = args.vsg_args.strip('"')
        use_shell = sys.platform == "linux"
        subprocess.run(f"vsg -c {config_file} {vsg_args}", check=True, shell=use_shell)
