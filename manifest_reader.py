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

from pathlib import Path
import yaml
from sys import platform as _platform

SIMULATORS = ["msim", "msim_free", "ghdl", "qsim", "xsim"]
DEFAULT_SIMULATORS = ["msim", "msim_free"]
DEFAULT_MAX_THREADS = 5


def main():
    """
    Main function for this module, only used for debug
    """
    manifest_dir = Path(__file__).resolve().parent
    manifest = read_manifest(manifest_dir)
    print(manifest)


def read_manifest(root_dir):
    """
    Read the manifest in the provided directory and returns a parsed
    `Manifest` object to represent it.

    Args:
        root_dir: The directory containing the manifest

    Returns:
        A `Manifest` object representing the block's manifest
    """
    root_dir = Path(root_dir)
    with open(root_dir / "manifest.yaml") as file:
        # The FullLoader parameter handles the conversion from YAML
        # scalar values to Python the dictionary format
        manifest_dict = yaml.load(file, Loader=yaml.FullLoader)

    manifest = Manifest(manifest_dict, root_dir)
    return manifest


class Manifest:
    """
    A `Manifest` class to represent a block's manifest

    Args:
        manifest_dict: The dictionary representing the manifest file,
        usually direct output of yaml.read
        root_dir: Root directory of the block, the folder containing the manifest

    Returns:
        A new `Manifest` object representing the provided dictionary
    """

    def __init__(self, manifest_dict, root_dir):
        self.root_dir = Path(root_dir)
        self.name = manifest_dict["name"]
        if "folder_structure" in manifest_dict:
            self.folder_structure = FolderStructure(manifest_dict["folder_structure"])
        else:
            self.folder_structure = None
        # Set default standard
        if "standard" in manifest_dict:
            default_standard = manifest_dict["standard"]
        else:
            default_standard = "VHDL"
        # Get any specific standards if they exist
        standards = None
        if "standards" in manifest_dict:
            standards = manifest_dict["standards"]
        self.file_lists = []
        for kind in manifest_dict["files"].keys():
            files = manifest_dict["files"][kind]
            standard = default_standard
            if kind == "tb":
                # Always use 2008 for testbenches
                standard = "VHDL 2008"
            elif standards is not None and kind in standards:
                # Otherwise get specific standard if applicable
                standard = standards[kind]
            # Add this file list to our file lists
            file_list = FileList(kind, files, standard)
            self.file_lists.append(file_list)

        self.blocks = manifest_dict["blocks"] if "blocks" in manifest_dict else None
        self.constraints = (
            manifest_dict["constraints"] if "constraints" in manifest_dict else None
        )
        self.ips = manifest_dict["ips"] if "ips" in manifest_dict else None
        self.supported_simulators = (
            manifest_dict["supported_simulators"]
            if "supported_simulators" in manifest_dict
            else DEFAULT_SIMULATORS
        )
        self.max_threads = (
            manifest_dict["max_threads"]
            if "max_threads" in manifest_dict
            else DEFAULT_MAX_THREADS
        )

    def get_source_dir(self, kind):
        """
        Gets the source directory for the provided kind of file in this manifest

        Args:
            kind: A valid library kind, see `FileList.kinds`

        Returns:
            The path to the folder containing files of this kind
        """
        if self.folder_structure is None:
            return self.root_dir
        return self.root_dir / self.folder_structure.structure[kind]

    def get_preferred_simulator(self):
        preference_order = ["ghdl", "qsim", "msim", "msim_free", "xsim"]
        for simulator in preference_order:
            if simulator in self.supported_simulators:
                return simulator

    def get_max_threads(self):
        return self.max_threads

    def get_all_files(self):
        """
        Returns all files in the manifest relative to the manifest

        Returns:
            A list of absolute paths to all files
        """
        ret = []
        for file_list in self.file_lists:
            files = file_list.files
            dir = self.get_source_dir(file_list.kind)
            paths = [(dir / file) for file in files]
            ret.extend(paths)
        return ret

    def __str__(self):
        """
        Stringifies the `Manifest`

        Returns:
            A string representing the `Manifest`
        """
        return str(self.__dict__)

    def __repr__(self):
        """
        Stringifies the `Manifest`

        Returns:
            A string representing the `Manifest`
        """
        return str(self)


class FileList:
    """
    Represents a list of files to manage standards and library names

    Args:
        kind: A valid library kind, see `FileList.kinds`
        files: A list of filenames to include in this list
        standard: The VHDL standard to use for this list, usually one of ("VHDL", "VHDL 2008)"

    Returns:
        A new `FileList` object
    """

    def __init__(self, kind, files, standard):
        self.kind = kind
        self.files = files
        self.standard = standard

    kinds = {"dsn": "_dsn", "tb": "_tb", "self": "_lib", "none": ""}

    def get_lib_name(self, blk_name):
        """
        Gets the name of the library for the given block

        Args:
            blk_name: The name of the block

        Returns:
            The proper name for the library for this file list and the provided block
        """
        return f"{blk_name}{FileList.kinds[self.kind]}"

    def __str__(self):
        """
        Stringifies the `FileList`

        Returns:
            A string representing the `FileList`
        """
        return str(self.__dict__)

    def __repr__(self):
        """
        Stringifies the `FileList`

        Returns:
            A string representing the `FileList`
        """
        return str(self)


class FolderStructure:
    """
    Represents a folder structure to allow for multiple structures mapping to the same information

    Args:
        folder_structure: A valid folder structure name, see `FolderStructure.folder_structures`

    Returns:
        A new `FolderStructure` to manage files under different folder structures
    """

    def __init__(self, folder_structure):
        self.name = (
            folder_structure
            if folder_structure in FolderStructure.folder_structures
            else None
        )
        self.structure = FolderStructure.folder_structures[folder_structure]

    folder_structures = {
        "src_dsn": {"dsn": "src/dsn", "tb": "src/tb", "self": ""},
        "hdl_sim": {"dsn": "..", "tb": ".", "self": ""},
    }

    def __str__(self):
        """
        Stringifies the `FolderStructure`

        Returns:
            A string representing the `FolderStructure`
        """
        return str(self.__dict__)

    def __repr__(self):
        """
        Stringifies the `FolderStructure`

        Returns:
            A string representing the `FolderStructure`
        """
        return str(self)


if __name__ == "__main__":
    main()
