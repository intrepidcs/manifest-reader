# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2020, Lars Asplund lars.anders.asplund@gmail.com

import sys
from pathlib import Path
from vunit.sim_if.factory import SIMULATOR_FACTORY
from vunit.vivado import (
    run_vivado,
    add_from_compile_order_file,
    create_compile_order_file,
)
import shutil

import blocks_reader
import manifest_reader

from os import environ


def clear_ip_search(output_path):
    """
    Clears the compile order file to run a clean search

    Args:
        output_path: VUnit's output path
    """
    to_del = Path(output_path) / "project_ip/compile_order.txt"
    if to_del.exists():
        to_del.unlink()


def add_vivado_ip(vunit_obj, output_path, project_file, vivado_path):
    """
    Add vivado (and compile if necessary) vivado ip to vunit project.
    """

    if project_file is not None and not Path(project_file).exists():
        print("Could not find vivado project %s" % project_file)
        sys.exit(1)

    opath = Path(output_path)

    standard_library_path = str(opath / "standard")
    compile_standard_libraries(vunit_obj, standard_library_path, vivado_path)

    if project_file is not None:
        project_ip_path = str(opath / "project_ip")
        add_project_ip(vunit_obj, project_file, project_ip_path, vivado_path)


def compile_standard_libraries(vunit_obj, output_path, vivado_path):
    """
    Compiles standard vivado libraries

    Args:
        vunit_obj: A `VUnit` object
        output_path: The output path
    """
    simulator_class = SIMULATOR_FACTORY.select_simulator()
    simname = simulator_class.name
    print(simname)
    if simname == "ghdl":
        _compile_standard_libraries_unsupported(vunit_obj, output_path, vivado_path)
    else:
        _compile_standard_libraries_supported(vunit_obj, output_path, vivado_path)
    # Clean up after Vivado
    for garbage_file in ("modelsim.ini", ".cxl.modelsim.version"):
        garbage_file = Path(garbage_file)
        if garbage_file.exists():
            garbage_file.unlink()


def _compile_standard_libraries_unsupported(vunit_obj, output_path, vivado_path):
    """
    Compiles standard vivado libraries for simulators that vivado doesn't
    actually support aka GHDL.
    This isn't really used right now but I am leaving it in case we can use it in the future
    It seemed to kind of work

    Args:
        vunit_obj: A `VUnit` object
        output_path: The output path
    """
    # Stub this out for now

    data_dir = Path(vivado_path) / "data/vhdl/src"
    # libs = {
    #     'unisim' : 'unisims',
    #     # 'unimacro' : 'unimacro',
    #     # 'unifast' : 'unifast',
    #     # 'synopsys' : 'synopsys'

    # }
    # vunit_libs = {}
    # for lib in libs:
    #     vunit_libs[lib] = vunit_obj.add_library(lib)
    # vunit_libs['secureip'] = vunit_obj.add_library('secureip')
    # for folder, lib in libs.items():
    #     files = (data_dir / folder / 'retarget').rglob('*.vhd')
    #     for file in files:
    #         if file.parent == 'secureip':
    #             vunit_libs['secureip'].add_source_files(file)
    #         else:
    #             vunit_libs[lib].add_source_files(file)

    unisim = vunit_obj.add_library("unisim")
    files = list((data_dir / "unisims").rglob("*.vhd"))
    secureip_files = []
    unisim_files = []
    for file in files:
        file = file.resolve()
        if "retarget" in str(file):
            # Ignore retarget stuff
            continue
        if file.parent.name == "secureip":
            secureip_files.append(file)
        else:
            unisim_files.append(file)
    # with open('files.txt', 'w+') as f:
    #     for file in unisim_files:
    #         f.write(str(file) + '\n')
    # exit()

    compile_options = "-fexplicit -frelaxed-rules --no-vital-checks --warn-binding --mb-comments --ieee=synopsys".split()

    unisim.add_source_files(unisim_files)
    unisim.set_compile_option("ghdl.a_flags", compile_options)
    # unisim.get_source_file('*PLLE4_BASE.vhd').add_dependency_on(unisim.get_source_file('*PLLE4_ADV.vhd'))

    secureip = vunit_obj.add_library("secureip")
    secureip.add_source_files(secureip_files)
    secureip.set_compile_option("ghdl.a_flags", compile_options)


def _compile_standard_libraries_supported(vunit_obj, output_path, vivado_path=None):
    """
    Compile Xilinx standard libraries using Vivado TCL command
    """
    done_token = str(Path(output_path) / "all_done.txt")

    simulator_class = SIMULATOR_FACTORY.select_simulator()

    if not Path(done_token).exists():
        print(
            "Compiling standard libraries into %s ..."
            % str(Path(output_path).resolve())
        )
        simname = simulator_class.name
        simulator_path = simulator_class.find_prefix().replace("\\", "/")

        # Vivado calls rivierapro for riviera
        if simname == "rivierapro":
            simname = "riviera"

        # Vivado differentiates between modelsim and questa
        if "questa" in simulator_path:
            simname = "questa"

        # They only provide 32 bit modelsim for linux?
        mode_32 = "-32bit" if sys.platform == "linux" and simname == "modelsim" else ""
        print(simulator_path)
        run_vivado(
            str(Path(__file__).parent / "tcl" / "compile_standard_libs.tcl"),
            tcl_args=[
                simname,
                simulator_path,
                output_path.replace("\\", "/"),
                mode_32,
            ],
            vivado_path=vivado_path,
        )

    else:
        print(
            "Standard libraries already exists in %s, skipping"
            % str(Path(output_path).resolve())
        )

    for library_name in [
        "unisims_ver",
        "unisim",
        "unimacro",
        "unimacro_ver",
        "unifast",
        "unifast_ver",
        "secureip",
        "xpm",
    ]:
        path = str(Path(output_path) / library_name)
        if Path(path).exists():
            vunit_obj.add_external_library(library_name, path)

    xilinxcorelib_ver = vunit_obj.add_library("xilinxcorelib_ver")
    vivado_base = Path(shutil.which("vivado")).parent.parent
    xilinxcorelib_ver.add_source_files(vivado_base / "data/verilog/src/glbl.v")

    with open(done_token, "w") as fptr:
        fptr.write("done")


def add_project_ip(vunit_obj, project_file, output_path, vivado_path=None, clean=False):
    """
    Add all IP files from Vivado project to the vunit project

    Caching is used to save time where Vivado is not called again if the compile order already exists.
    If Clean is True the compile order is always re-generated

    returns the list of SourceFile objects added
    """

    compile_order_file = str(Path(output_path) / "compile_order.txt")

    if clean or not Path(compile_order_file).exists():
        create_compile_order_file(
            project_file, compile_order_file, vivado_path=vivado_path
        )
    else:
        print(
            "Vivado project Compile order already exists, re-using: %s"
            % str(Path(compile_order_file).resolve())
        )

    return add_from_compile_order_file(vunit_obj, compile_order_file)


def get_build_standard(path, file_list):
    """
    Gets the vivado build string for the provided path type

    Args:
        path: An HDL file of some kind
        manifest: The `Manifest` object this file is contained in

    Returns:
        The proper vivado string
    """
    # Handle verilog files specially
    if path.suffix in (".svh", ".vh"):
        standard = "Verilog Header"
    elif path.suffix in (".v", ".sv"):
        standard = "Verilog"
    else:
        standard = file_list.standard
    return standard


def get_ip_standard(path, file_list):
    """
    Gets the vivado ip string for the provided path type

    Args:
        path: An HDL file of some kind
        manifest: The `Manifest` object this file is contained in

    Returns:
        The proper vivado string
    """
    # Handle verilog files specially
    if path.suffix in (".svh", ".vh"):
        standard = "verilogSource"
    elif path.suffix in (".v", ".sv"):
        standard = "verilogSource"
    else:
        if file_list.standard == "VHDL":
            standard = "vhdlSource"
        else:
            standard = "vhdlSource-2008"

    return standard


def get_standard(path, file_list, for_ip):
    """
    Gets the vivado string for the provided path type
    Uses IP string when for_ip, else build string

    Args:
        path: An HDL file of some kind
        manifest: The `Manifest` object this file is contained in
        for_ip: When true, generates the string used for IP packager

    Returns:
        The proper vivado string
    """
    if for_ip:
        standard = get_ip_standard(path, file_list)
    else:
        standard = get_build_standard(path, file_list)
    standard = "{" + standard + "}"
    return standard


def generate_filelist(
    root_dir, proj_dir, relative_to=None, for_ip=False, other_files=None
):
    """
    Generates a tcl filelist for the project to be read by a build script
    Writes the file to root_dir

    Args:
        root_dir:    The root of the repo
        proj_dir:    The directory the vivado project will go in
        relative_to: When set, paths will be generated relative to this rather than absolute
        for_ip:      When true, generates IP file standards instead of build standards
        other_files: Optional extra files.  Format is as follows for design files.  Others not yet implemented
                     {"vhdl":
                         {lib_name: {
                             [(file, standard)]
                         }
                     } where standard is [VHDL, VHDL 2008]
    """
    blk_dirs = blocks_reader.read_blocks(environ.get("BASE_DIR"))
    files = []
    for blk_dir in blk_dirs:
        manifest = manifest_reader.read_manifest(blk_dir)
        for file_list in manifest.file_lists:
            lib_name = file_list.get_lib_name(manifest.name)
            lib_name = "{" + lib_name + "}"
            # Skip tb files
            if file_list.kind == "tb":
                continue
            for file in file_list.files:
                path = (manifest.get_source_dir(file_list.kind) / file).resolve()
                if relative_to is not None:
                    path = path.relative_to(relative_to)
                standard = get_standard(path, file_list, for_ip)
                path = "{" + str(path).replace("\\", "/") + "}"
                files.append([path, lib_name, standard])
        if manifest.constraints is not None and not for_ip:
            for constraint_file in manifest.constraints:
                path = str((manifest.root_dir / constraint_file).resolve())
                path = "{" + path + "}"
                files.append([path, "{N/A}", "{xdc}"])
        if manifest.ips is not None and not for_ip:
            for ip in manifest.ips:
                path = str(
                    (manifest.root_dir / f"ip/{str(ip)}" / (str(ip) + ".xci")).resolve()
                )
                path = "{" + path + "}"
                files.append([path, "{N/A}", "{N/A}"])

    if other_files:
        vhdl_libs = other_files["vhdl"]
        for lib_name, data in vhdl_libs.items():
            for file, standard in data:
                standard = f"{{{standard}}}"
                path = file
                if relative_to is not None:
                    path = path.relative_to(relative_to)
                path = "{" + str(path).replace("\\", "/") + "}"
                files.append([path, lib_name, standard])
        constraints = other_files["xdc"]
        for constraint in constraints:
            path = str(constraint)
            path = "{" + path + "}"
            files.append([path, "{N/A}", "{xdc}"])

    to_write = "set all_sources [list \\\n"
    for file in files:
        to_write += f'\t{" ".join(file)} \\\n'
    to_write += "]\n"

    filelist_path = (Path(proj_dir) / "filelist.tcl").resolve()
    print(filelist_path)
    parent = filelist_path.parent
    if not parent.exists():
        parent.mkdir(parents=True)
    with open(filelist_path, "w+") as f:
        f.write(to_write)


def update_ip(root_dir, proj_dir):
    """
    Updates the IP as necessary by updated the component.xml with all files

    Args:
        root_dir: The root of the repo
        proj_dir: The directory the vivado project will go in
    """
    generate_filelist(root_dir, proj_dir, relative_to=root_dir, for_ip=True)
    run_vivado(
        str(Path(__file__).parent / "tcl" / "update_ip.tcl"),
        tcl_args=[root_dir / "component.xml", proj_dir / "filelist.tcl"],
    )
