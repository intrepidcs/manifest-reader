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
from vunit import VUnit, VUnitCLI
from vunit.sim_if import SimulatorInterface, check_output
from vunit.sim_if.modelsim import encode_generic_value, fix_path
from vunit.sim_if.factory import SIMULATOR_FACTORY
from vunit.test.list import TestList
from vunit.test.bench_list import TestBenchList
from vunit.test.suites import TestRun
from vunit.builtins import Builtins
from vunit.source_file import SourceFile, VHDLSourceFile
from vunit.test.bench_list import tb_filter
from vunit.project import Project
from vunit.color_printer import COLOR_PRINTER, NO_COLOR_PRINTER
from vunit.ui.common import (
    select_vhdl_standard,
    SIMULATORS,
    WIN_INSTALL_LOCATIONS,
    LINUX_INSTALL_LOCATIONS,
)
from vivado_util import add_vivado_ip, clear_ip_search
from generate_vivado_project import generate_vivado_project
from fnmatch import fnmatch
from vunit import ui
import os
import manifest_reader
from os import environ
import itertools
from typing import Union, Optional
import yaml
import inspect
import subprocess
import argparse
from pprint import pprint
import sys
import re
from shutil import rmtree
import types
import subprocess
import shutil

XILINX_BIN_EXTENSION = ".bat" if sys.platform == "win32" else ""


def main():
    """
    Main function, only used for debug
    """
    parser = get_parser()
    args = parser.parse_args()
    blk_dirs = [Path(__file__).resolve().parent / "test_blk"]
    run_vunit(args, blk_dirs)


def get_parser():
    """
    Gets a vunit parser with some extended arguments that we use.
    Additional arguments can then be added by the individual test if needed

    Returns:
        An `argparse.ArgumentParser` object
    """
    cli = VUnitCLI()
    parser = cli.parser
    parser.formatter_class = argparse.ArgumentDefaultsHelpFormatter
    parser.add_argument(
        "--show-pass",
        action="store_true",
        help="Show passing checks in testbenches",
        default=False,
    )
    parser.add_argument(
        "-s",
        "--stop-on-bad-check",
        action="store_true",
        help="Stop the simulation on the first bad check",
        default=False,
    )
    parser.add_argument(
        "--debug-print",
        action="store_true",
        help="Enable simulation debug prints",
        default=False,
    )
    parser.add_argument(
        "--reload-project",
        action="store_true",
        help="Use this after changing the vivado project to recheck IP",
        default=False,
    )
    parser.add_argument(
        "-w",
        "--fail-on-warning",
        action="store_true",
        help="Fail the sim if a warning occurs",
        default=False,
    )
    parser.add_argument(
        "--no-optimization",
        action="store_true",
        help="Turns off compiler optimizations, set if your signals aren't visible in waveform",
        default=False,
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Enable coverage reporting.  Files are always compiled with coverage, this just enables simulation tracking/reporting",
        default=False,
    )
    parser.add_argument(
        "--no-prompts",
        action="store_true",
        help="Disable any pre-sim prompts and always take suggested default.  Generally only for CI builds",
        default=False,
    )
    return parser


def setup_vunit(
    args,
    blk_dirs,
    use_vivado_ip=None,
    vivado_project=None,
    disable_ieee_warnings=False,
    use_preprocessing=True,
    vivado_version=None,
):
    """
    Takes care of boilerplate setup for vunit

    Args:
        args: The parsed arguments to use, usually the output of args.parse_args()
        blk_dirs: List of directories that contain blocks with manifests
        use_vivado_ip: When True, compiles all available vivado libraries
        vivado_project: When not None, points to a .xpr file containing instantiated IP.
        The project will be parsed for IP and its output artifacts compiled for use in the simulation
        disable_ieee_warnings: When True, disables some usually spammed warnings from ieee
        use_preprocessing: Allow vunit to copy files to a preprocessing folder, should always be on for sim runs
        vivado_version: Optional specification of which vivado version the vivado ip is compatible with

    Returns:
        A new `Vunit` object with all files from the provided blocks added and most configurations set
        The output can be directly run with `run_vunit_main` if no additional test configs are required,
        otherwise add your test configs as necessary
    """
    simulator_install_dir = set_simulator(args.simulator)
    # print(simulator_install_dir)
    # exit()
    num_cores = os.cpu_count()
    if args.num_threads > num_cores:
        print(
            f"{args.num_threads} threads requested, but machine has only {num_cores} cores"
        )
        print(
            f"This will likely cause cache thrashing and other scary things.  Throttling to {num_cores} threads"
        )
        args.num_threads = num_cores
    if args.simulator == "msim":
        # Check that requested licenses are available and throttle them if necessary
        num_licenses_available = get_num_licenses_available(simulator_install_dir)
        if num_licenses_available == 0:
            print(
                "Uh-Oh, all licenses are taken :( Giving you one to be put in the queue"
            )
            args.num_threads = 1
        elif num_licenses_available < args.num_threads:
            print(
                f"Hm, looks like you want {args.num_threads} threads, but only {num_licenses_available} licenses are available"
            )
            if args.no_prompts or yes_input(
                f"Okay to be throttled to {num_licenses_available} threads? (If not, it'll work, you'll just spend more time in the queue"
            ):
                print(
                    f"Throttling to {num_licenses_available} threads due to license constraints"
                )
                args.num_threads = num_licenses_available
            else:
                print(
                    f"Keeping {args.num_threads} threads, watch out for the people yelling at you that their sims are slower!"
                )

    root_dir = Path(os.getenv("BASE_DIR"), ".")
    args.output_path = root_dir / "scratch/vunit_out"
    # For some reason riviera tends to choke on long running batch jobs when running in persistent process
    # Vunit docs say this causes a slowdown, unsure how much
    # For now just always enable unique sims for riviera
    # TODO Figure out how to fix this
    if args.simulator == "riviera":
        args.unique_sim = True

    # It appears linux has a limitation on the individual components of a path, even though the entire thing is unlimited
    # This will make the paths only be hashes instead of some portion of the test name + hash
    # We use the utility to get test paths anyways so the longer ones are just clutter
    environ["VUNIT_SHORT_TEST_OUTPUT_PATHS"] = str(True)

    # We lose output sometimes, this is a general python flag to force stdout to flush always
    # Have not noticed performance decrease but may want to watch out for them
    environ["PYTHONUNBUFFERED"] = str(True)

    vu = VUnit.from_args(args)
    # exit()

    if use_preprocessing:
        vu.enable_check_preprocessing()
        vu.enable_location_preprocessing()

    # We'll need this for coverage later, store it off as a new attribute
    setattr(vu, "_simulator_install_dir", simulator_install_dir)

    coverage_enabled = False
    if args.coverage:
        if args.simulator == "riviera" or args.simulator == "msim":
            # Only enable coverage for riviera as modelsim free does not support
            coverage_enabled = True

    # Create new attribute at runtime for the post check to see if coverage should be reported
    setattr(vu, "coverage_enabled", coverage_enabled)

    for blk_dir in blk_dirs:
        vu = add_files_from(blk_dir, vu, args, root_dir)

    if use_vivado_ip and args.simulator and args.simulator != "ghdl":
        if vivado_version is None:
            vivado_version = "2019.1"
        vivado_cmd = get_vivado_cmd(vivado_version)
        vivado_path = vivado_cmd.parent.parent
        output_path = args.output_path / "vivado_libs" / args.simulator
        if args.reload_project:
            clear_ip_search(output_path)
        add_vivado_ip(
            vu,
            output_path=output_path,
            project_file=vivado_project,
            vivado_path=vivado_path,
        )
        # Xilinx is strange and adds this magical glbl.v to simulate GSR
        # Not sure what it does in the background, but needs to be considered a top level for all testbenches
        # using it, like PLLs.  Add the equivalent command here for any used simulators
        for vsim_if in ("modelsim", "rivierapro"):
            if args.simulator == "qsim":
                continue
            vu.set_sim_option(
                f"{vsim_if}.vsim_flags",
                [f"xilinxcorelib_ver.glbl"],
                overwrite=False,
                allow_empty=True,
            )

    vu.set_sim_option(
        "modelsim.vsim_flags", ["-error", "3473"], overwrite=False, allow_empty=True
    )
    vu.set_sim_option(
        "rivierapro.vsim_flags", ["-unbounderror"], overwrite=False, allow_empty=True
    )
    vu.set_sim_option(
        "ghdl.sim_flags", ["--max-stack-alloc=0"], overwrite=False, allow_empty=True
    )
    vu.set_sim_option(
        "ghdl.elab_flags", ["-frelaxed"], overwrite=False, allow_empty=True
    )
    # print(vu._project.get_source_files_in_order())
    # print(vu._test_bench_list.get_test_benches())
    vu.set_sim_option(
        "rivierapro.init_file.gui",
        str(Path(__file__).parent / "tcl" / "riviera_gui.tcl"),
    )
    vu.set_sim_option(
        "modelsim.init_file.gui",
        str(Path(__file__).parent / "tcl" / "modelsim_gui.tcl"),
    )

    if coverage_enabled:
        if coverage_enabled:
            vu.set_sim_option("enable_coverage", True)
        vu.set_sim_option(
            "rivierapro.vsim_flags",
            ["-cc_hierarchy", "-cc_all"],
            overwrite=False,
            allow_empty=True,
        )
        vu.set_sim_option(
            "modelsim.vsim_flags", ["-coverage"], overwrite=False, allow_empty=True
        )

    vu.add_osvvm()
    vu.add_verification_components()

    tb_cfg = {
        "stop_on_bad_check": args.stop_on_bad_check,
        "show_pass": args.show_pass,
        "debug_print": args.debug_print,
        "fail_on_warning": args.fail_on_warning,
    }
    encoded_tb_cfg = ", ".join(["%s:%s" % (key, str(tb_cfg[key])) for key in tb_cfg])

    vu.set_sim_option("disable_ieee_warnings", disable_ieee_warnings, allow_empty=True)

    vu.set_generic("tb_cfg", encoded_tb_cfg, allow_empty=True)

    override_compile(vu, args.simulator)

    return vu


def run_vunit_main(vu):
    """
    Wrapper around running vunit to handle any tasks we need to do before running

    Args:
        vu: A `Vunit` object to run
    """
    override_read_results(vu)
    output_path = Path(vu._output_path) / "coverage"
    coverage_db = str((output_path / "coverage.acdb").resolve())
    coverage_report = str((output_path / "coverage.html").resolve())
    coverage_db_escaped = coverage_db.replace("\\", "/")
    coverage_report_escaped = coverage_report.replace("\\", "/")
    modelsim_output_folder = Path("covhtmlreport")
    modelsim_output_path = output_path / modelsim_output_folder
    if not output_path.exists():
        output_path.mkdir()

    def post_run(results):
        if vu.coverage_enabled:
            prefix = vu._simulator_install_dir
            vsim = str((prefix / "vsim").resolve()).replace("\\", "/")
            vcover = str((prefix / "vcover").resolve()).replace("\\", "/")
            if vu.get_simulator_name() == "rivierapro":
                report_cmds = (
                    vsim,
                    "-c",
                    "-do",
                    f"acdb report -db {coverage_db_escaped} -html -o {coverage_report_escaped}",
                )
            elif vu.get_simulator_name() == "modelsim":
                report_cmds = (
                    (
                        vcover,
                        "report",
                        "-html",
                        "-details",
                        "-annotate",
                        f"{coverage_db_escaped}",
                    ),
                    (
                        vcover,
                        "report",
                        "-output",
                        f"{modelsim_output_folder / 'coverage.txt'}",
                        f"{coverage_db_escaped}",
                    ),
                )
            results.merge_coverage(file_name=coverage_db)
            for cmd in report_cmds:
                print(f"Running command {cmd}")
                subprocess.run(cmd)
            if modelsim_output_folder.exists():
                if modelsim_output_path.exists():
                    rmtree(modelsim_output_path)
                modelsim_output_folder.rename(output_path / modelsim_output_folder)

    vu.main(post_run=post_run)


def run_vunit(
    args, blk_dirs, use_vivado_ip=None, vivado_project=None, disable_ieee_warnings=False
):
    """
    Takes care of boilerplate setup for vunit and runs vunit

    Args:
        args: The parsed arguments to use, usually the output of args.parse_args()
        blk_dirs: List of directories that contain blocks with manifests
        use_vivado_ip: When True, compiles all available vivado libraries
        vivado_project: When not None, points to a .xpr file containing instantiated IP.
        The project will be parsed for IP and its output artifacts compiled for use in the simulation
        disable_ieee_warnings: When True, disables some usually spammed warnings from ieee
    """
    vu = setup_vunit(
        args, blk_dirs, use_vivado_ip, vivado_project, disable_ieee_warnings
    )
    run_vunit_main(vu)


def to_vunit_vhdl_standard(standard):
    """
    Simple converter functions for translating version strings to what vunit wants them to be

    Args:
        standard: One of ("VHDL", "VHDL 2008")

    Returns:
        The equivalent version string for vunit
    """
    if standard == "VHDL":
        return "93"
    elif standard == "VHDL 2008":
        return "2008"
    return "UNSPECIFIED_STANDARD"


def get_vivado_cmd(version):
    """
    Determines the command to be used to run the requested vivado version
    Search order is PATH, FPGA_BUILDER_VIVADO_{VERSION}_INSTALL_DIR, default Xilinx Path
    {VERSION} for "2019.1" would be "2019_1"

    Args:
        version: String representing the vivado version, i.e. "2019.1"

    Returns:
        A Path to the vivado command to use

    Raises:
        If no search paths find this vivado version, exits with code

    """
    vivado_cmd = shutil.which("vivado")
    if vivado_cmd is not None:
        vivado_version = Path(vivado_cmd).parent.parent.name
        if vivado_version == version:
            # Easy enough, the one on path was what we wanted
            return Path(vivado_cmd)

    # Didn't find it, look through environment variables
    version_name = version.replace(".", "_")
    builder_vivado_env_var = f"FPGA_BUILDER_VIVADO_{version_name}_INSTALL_DIR"
    if builder_vivado_env_var in environ:
        vivado_install_dir = Path(environ.get(builder_vivado_env_var))
        if vivado_install_dir.exists():
            vivado_cmd = vivado_install_dir / f"bin/vivado{XILINX_BIN_EXTENSION}"
            return vivado_cmd
        else:
            print(
                f"Specified install dir from {builder_vivado_env_var} was {vivado_install_dir}, but does not exist"
            )
            exit(1)

    # Last chance, try guessing off the usual install path
    vivado_cmd = Path(f"C:/Xilinx/Vivado/{version}/bin/vivado{XILINX_BIN_EXTENSION}")
    if vivado_cmd.exists():
        return vivado_cmd

    # Couldn't find anything, die :(
    print(
        f"ERROR: Vivado {version} not found.  Run setup script or set {builder_vivado_env_var}"
    )
    exit(1)


def override_create_tests(vu):
    """
    Hackily hacked hack to hotswap vunit function to generate tests
    Needed to add option to only run first test matching filter instead of all
    In future we may fork VUnit which would eliminate the need for this

    Args:
        vu: A `Vunit` object

    """
    # Modify the private instance method of the vunit object to do whatever it usually does
    # But then only keep the first thing it returned
    orig_create_tests = vu._create_tests

    def _create_tests_first_test_only(
        self, simulator_if: Union[None, SimulatorInterface]
    ):
        orig_list = orig_create_tests(simulator_if)
        if orig_list is not None and len(orig_list) > 0:
            first = orig_list[0]
            ret = TestList()
            ret._test_suites = [orig_list._test_suites[0]]
            return ret
        return orig_list

    override_instance_method(vu, orig_create_tests, _create_tests_first_test_only)


def gen_configs(test_cfg_options):
    """
    Utils function to permute all possible options of the provided configurations

    Args:
        test_cfg_options: A dictionary of the form {"cfg1": ["option1", "option2"], "cfg2": ["option1", "option2"]}

    Returns:
        A list of dictionaries where each element contains one permutation of the provided dictionary of lists
    """
    # Get all the values and unpack to get a bunch of lists, permute all of them
    permutations = itertools.product(*test_cfg_options.values())
    configs = []
    for permutation in permutations:
        test_cfg = {}
        # For each permutation, given that they are in the same order as provided in the dictionary, label them
        for i, key in enumerate(test_cfg_options):
            # Map the property being configured to its value in this permutation
            test_cfg[key] = permutation[i]

        # Add it to the list
        configs.append(test_cfg)

    return configs


def add_config(config, item):
    """
    Utils function to add the provided configuration to the provided item (can mostly be any Vunit-like object)

    Args:
        config: A dictionary containing the configuration to add
        item: A Vunit-like object, usually a `TestBench`
    """
    # Encode it into a dictionary to pass in as the generic
    config_name = ""
    for i, (k, v) in enumerate(config.items()):
        config_name += f"{k}={v}"
        if i != len(config) - 1:
            config_name += ","
    encoded_test_cfg = {}
    encoded_test_cfg["test_cfg"] = ", ".join(
        ["%s:%s" % (key, str(config[key])) for key in config]
    )
    item.add_config(name=config_name, generics=encoded_test_cfg)


def add_all_configs(test_cfg_options, item):
    """
    Utils function to add all of the possible configurations of the provided options to the item
    Use this as a shortcut if configurations are used and none need to be constrained/filtered out

    Args:
        test_cfg_options: A dictionary of the form {"cfg1": ["option1", "option2"], "cfg2": ["option1", "option2"]}
        item: A Vunit-like object, usually a `TestBench`
    """
    configs = gen_configs(test_cfg_options)
    for config in configs:
        add_config(config, item)


def override_read_results(vu):
    """
    Hackily hacked hack to generate an alternate read_test_results function that also exports status to a file for us to read
    Add this to VUnit if we fork

    Args:
        vu: A `Vunit` object

    """
    orig_read_test_results = TestRun._read_test_results
    all_tests = {
        str(test_name): "running"
        for test_name in vu._create_tests(simulator_if=None).test_names
    }

    def dump(all_tests):
        """
        Gathers test status and generates a text file to represent the status

        Args:
            all_tests: A dictionary of strings of the form {full_test_name: status}
        """
        ordered_tests = {}
        ordered_tests.update(
            {test: result for test, result in all_tests.items() if result == "failed"}
        )
        ordered_tests.update(
            {test: result for test, result in all_tests.items() if result == "passed"}
        )
        ordered_tests.update(
            {test: result for test, result in all_tests.items() if result == "skipped"}
        )
        ordered_tests.update(
            {test: result for test, result in all_tests.items() if result == "running"}
        )
        ordered_tests.update(
            {
                test: result
                for test, result in all_tests.items()
                if result not in ["failed", "passed", "skipped", "running"]
            }
        )
        while True:
            # Have to do this for when we're running multiple threads and they fight for access
            try:
                with open(Path(vu._args.output_path / "test_status.txt"), "w+") as file:
                    for test, result in ordered_tests.items():
                        file.write(f"{result} : {test}\n")
                break
            except OSError:
                pass

    dump(all_tests)

    def _read_test_results_and_write_to_file(self, file_name):
        """
        Alternate read_test_results function that also exports status to a file for us to read
        Add this to VUnit if we fork

        Args:
            file_name: The name of the internal VUnit result file, will be populate by VUnit

        Returns:
            Not really sure.  Some sort of object representing the results.  Just passes it back to VUnit
        """
        results = orig_read_test_results(self, file_name)
        # For our purpose this is always a single entry because we never run with combined sim instance
        # results is indexed by test name, we need the full name with path/config/etc
        first_result = next(iter(results.values()))
        all_tests[self._test_suite_name] = first_result.name
        dump(all_tests)
        return results

    TestRun._read_test_results = _read_test_results_and_write_to_file


def gen_prj_default(
    blk_dirs, vivado_project=None, use_vivado_ip=True, vivado_version=None
):
    """
    Utils function to generate a default VUnit project containing the provided blocks

    Args:
        blk_dirs:       A list of directories of blocks to add to the project
        vivado_project: Optional path to an xpr with IP that needs to be included
        use_vivado_ip:  Set to False if no XPM/unisim IP needed, speeds up compile time drastically
        vivado_version: Optional specification of which vivado version the vivado ip is compatible with

    Returns:
        A valid `VUnit` object with all the provided blocks added, default arguments, etc.
    """
    parser = get_parser()
    args = parser.parse_args()

    blk_dirs = [Path(blk_dir) for blk_dir in blk_dirs]
    vu = setup_vunit(
        args,
        blk_dirs,
        use_vivado_ip=use_vivado_ip,
        disable_ieee_warnings=True,
        vivado_project=vivado_project,
        vivado_version=vivado_version,
    )
    return vu


def run_vunit_main_default(
    blk_dirs,
    add_test_configs_func=None,
    tb=None,
    vivado_project=None,
    use_vivado_ip=True,
    vivado_version=None,
):
    """
    Runs vunit with all defaults for the provided blocks, optionally also running the provided
    add test config function

    Args:
        blk_dirs:              A list of directories of blocks to add to the project
        add_test_configs_func: Optional function to run that adds configurations to the project
        tb:                    Optional name of the library containing the testbench, if not provided will be inferred
        vivado_project:        Optional path to an xpr with IP that needs to be included
        use_vivado_ip:         Set to False if no XPM/unisim IP needed, speeds up compile time drastically
        vivado_version:        Optionally specify what vivado version is compatible if IP used
    """
    if tb is None:
        tb = get_nearest_tb(Path(inspect.stack()[1].filename).resolve())
    prj = gen_prj_default(
        blk_dirs,
        vivado_project=vivado_project,
        use_vivado_ip=use_vivado_ip,
        vivado_version=vivado_version,
    )
    tb_obj = prj.library(tb).entity(tb)
    if add_test_configs_func is not None:
        vu = add_test_configs_func(prj, tb_obj)
    run_vunit_main(vu)


def get_nearest_tb(filepath):
    """
    Infers the name of the nearest testbench library to the provided filepath

    Args:
        filepath: Any file, but probably the run.py for the current project

    Returns:
        A string representing the name of the library for the closest testbench to the file
    """
    parent = filepath.parent
    while parent is not None and parent.parent != parent:
        if "manifest.yaml" in (f.name for f in parent.iterdir()):
            manifest = manifest_reader.read_manifest(parent)
            tb_list = [
                file_list for file_list in manifest.file_lists if file_list.kind == "tb"
            ][0]
            if tb_list is not None:
                lib_name = tb_list.get_lib_name(manifest.name)
                return lib_name
        parent = parent.parent
    return None


def set_simulator(simulator_name):
    """
    Sets required environment variables for vunit to find our selected simulator

    Searches valid install paths as necessary to set the specific version of the simulator

    Args:
        simulator_name: A key in SIMULATORS, the desired simulator

    Returns:
        The path to a valid install if one is found

    """
    if simulator_name is None:
        return None
    simulator = SIMULATORS[simulator_name]
    environ["VUNIT_SIMULATOR"] = simulator["vunit_name"]
    searched_patterns = []
    if sys.platform == "win32":
        install_locations = WIN_INSTALL_LOCATIONS
        os_pattern = "win_path_pattern"
    else:
        install_locations = LINUX_INSTALL_LOCATIONS
        os_pattern = "linux_path_pattern"
    for root in install_locations:
        root = root.expanduser()
        pattern = simulator[os_pattern]
        if "*" in pattern:
            installs = list(root.glob(pattern))
        else:
            install = root / pattern
            installs = [install] if install.exists() else []

        if not installs:
            install_pattern = str((root / pattern).resolve())
            searched_patterns.append(install_pattern)
            continue

        if len(installs) > 1:
            if simulator_name == "ghdl":
                # Pick a ghdl preference
                installs = [install for install in installs if "gcc" in str(install)]
        assert len(installs) == 1, (
            "found multiple installs, default selection not yet implemented, uh oh...\n"
            + str(installs)
        )
        install = str(installs[0].resolve())
        environ[f"VUNIT_{simulator['vunit_name'].upper()}_PATH"] = install
        # override_vunit_init(simulator_name)
        return Path(install)
    print(
        f"Unable to locate simulator install for {simulator_name}.  Searched the following patterns:"
    )
    pprint(searched_patterns)
    exit(1)


def override_vunit_init(simulator_name):
    """
    Hackily hacked hack to hotswap vunit init function
    Necessary so that we can support multiple variants of a given simulator type
    Simply renames the compile artifact output directories so they are unique
    Sad that this is in init and not somewhere easier to mock :(

    Args:
        simulator_name: A key in SIMULATORS

    """

    def custom_vunit_init(
        self,
        args,
        compile_builtins: Optional[bool] = True,
        vhdl_standard: Optional[str] = None,
    ):
        self._args = args
        self._configure_logging(args.log_level)
        self._output_path = str(Path(args.output_path).resolve())

        if args.no_color:
            self._printer = NO_COLOR_PRINTER
        else:
            self._printer = COLOR_PRINTER

        def test_filter(name, attribute_names):
            keep = any(fnmatch(name, pattern) for pattern in args.test_patterns)

            if args.with_attributes is not None:
                keep = keep and set(args.with_attributes).issubset(attribute_names)

            if args.without_attributes is not None:
                keep = keep and set(args.without_attributes).isdisjoint(attribute_names)
            return keep

        self._test_filter = test_filter
        self._vhdl_standard: VHDLStandard = select_vhdl_standard(vhdl_standard)

        self._external_preprocessors = []  # type: ignore
        self._location_preprocessor = None
        self._check_preprocessor = None

        self._simulator_class = SIMULATOR_FACTORY.select_simulator()

        # Use default simulator options if no simulator was present
        if self._simulator_class is None:
            simulator_class = SimulatorInterface
            self._simulator_output_path = str(Path(self._output_path) / "none")
        else:
            simulator_class = self._simulator_class
            self._simulator_output_path = str(Path(self._output_path) / simulator_name)

        self._create_output_path(args.clean)

        database = self._create_database()
        self._project = Project(
            database=database,
            depend_on_package_body=simulator_class.package_users_depend_on_bodies,
        )

        self._test_bench_list = TestBenchList(database=database)

        self._builtins = Builtins(self, self._vhdl_standard, simulator_class)
        if compile_builtins:
            self.add_builtins()

    VUnit.__init__ = custom_vunit_init


def override_instance_method(obj, orig_func, new_func):
    """
    Overrides the instance method of the object with the new version
    Only exists so we can modify vunit live without branching

    Args:
        obj:       The object with an instance method to override
        orig_func: The original function, i.e. obj.some_function
        new_func:  The new function, must take in the same parameters as orig_func

    """
    # Python's fancy auto-diverging pointers suck in this case
    # We can't use the actual orig_func since it will stop pointing to the object's version once modified
    # So we figure out the string version of it
    try:
        orig_func_attr_string = orig_func.__name__
    except AttributeError:
        orig_func_attr_string = orig_func
    # Then figure out what kind of function the original was
    func_type = type(orig_func)
    # Then convert this into an instance method for the object
    new_func_as_instance_method = func_type(new_func, obj)
    # And finally set the attribute of the object
    orig_func_attached_to_instance = setattr(
        obj, orig_func_attr_string, new_func_as_instance_method
    )


def yes_input(prompt):
    """
    Adds boilerplate yes-like stuff to input to return True when yes
    Appends y/n to the end to be easier to follow

    Args:
        prompt:  The prompt text

    Returns:
        True if the input is yes-like, else False

    """
    return input(f"{prompt} (y/n): ").lower() in ("yes", "y")


def get_num_licenses_available(simulator_install_dir):
    """
    Checks how many licenses are available for the simulator
    Currently only works for modelsim, I think

    Args:
        simulator_install_dir:  Path to binaries folder of the simulator

    Returns:
        Number of licenses available to be used

    """
    lmutil = str((simulator_install_dir / "lmutil").resolve())
    # The license path is hardcoded because searching all takes forever
    # Maybe a way to do it without hardcoding, for now this is way faster and probably won't change
    # Bleh - VPN doesn't do DNS so hardcode the IP for now too :(
    server = os.environ["LM_LICENSE_FILE"]
    args = ["lmstat", "-a", "-c", server]
    try:
        result = subprocess.run([lmutil] + args, capture_output=True)
        output = str(result.stdout)
        lines = re.split(r"\\+n", output)
        error = result.returncode != 0

        if result.returncode:
            print(
                "Uh-Oh, something went wrong with checking for licenses :(.   Assuming 8?"
            )
            print(lines)
            return 8
    except FileNotFoundError:
        print("Some 32 bit library problem I haven't figured out yet.")
        print("Assuming 8 licenses available")
        return 8

    vsim_lines = [line for line in lines if "Users of msimpevsim:" in line]
    if not vsim_lines:
        print("Uh-oh, something went wrong parsing the lmstat output.  Assuming 8?")
        return 8
    vsim_line = vsim_lines[0]
    pattern = re.compile(
        r"Total of (?P<num_total>[0-9]+) license(s)? issued; *Total of (?P<num_used>[0-9]+) license(s)? in use"
    )
    matches = [m.groupdict() for m in pattern.finditer(vsim_line)]
    if not matches:
        print(
            "Uh-oh, something went wrong parsing the lmstat output.  Assuming 8?",
            vsim_line,
        )
        return 8
    matches = matches[0]
    num_avail = int(matches["num_total"]) - int(matches["num_used"])
    return num_avail


def add_files_from(blk_dir, vu, args, root_dir):
    """
    Reads the manifest for the given blk dir and adds all files within it with appropriate options

    Args:
        blk_dir:  Path to the block directory
        vu:       The Vunit object
        args:     The argparse arguments
        root_dir: The root of the repository

    Returns:
        The modified vunit object

    """
    try:
        # If there exists a relative path from here to root dir then it must be local
        rel_path = Path(blk_dir).resolve().relative_to(root_dir)
        as_ref = False
    except:
        # Otherwise it's external, tell read_manifest it's only a reference and we don't want its testbenches
        as_ref = True

    manifest = manifest_reader.read_manifest(blk_dir)
    if (
        args.simulator is not None
        and args.simulator not in manifest.supported_simulators
    ):
        # Don't try to compile blocks we can't compile
        return vu
    for file_list in manifest.file_lists:
        lib = vu.add_library(file_list.get_lib_name(manifest.name))
        lib = add_files_to_lib(lib, file_list, manifest, as_ref, vu)

        if file_list.kind == "dsn":
            lib.add_compile_option(
                "modelsim.vcom_flags",
                ["-check_synthesis", "-error", "1400,1401"],
                allow_empty=True,
            )
        elif file_list.kind == "tb":
            lib.add_compile_option(
                # For now to work around shared variable illegal usage
                "ghdl.a_flags",
                ["-frelaxed"],
                allow_empty=True,
            )
        lib.add_compile_option(
            "rivierapro.vcom_flags", ["-coverage", "sbe", "-incr"], allow_empty=True
        )
        lib.add_compile_option(
            "modelsim.vcom_flags", ["+cover=sbcexf"], allow_empty=True
        )
        if not args.no_optimization:
            # I want to only turn this on for batch runs but it will require vunit changes
            # Need to cache all compile results and be able to hotswap them as necessary
            # For now just provide an option
            lib.add_compile_option("rivierapro.vcom_flags", ["-O3"], allow_empty=True)
    # print(vu._test_bench_list.get_test_benches())
    # print(vu._project.get_source_files_in_order())
    return vu


def add_files_to_lib(lib, file_list, manifest, as_ref, vu):
    """
    Adds the files in the file list to the library with the given standard

    Args:
        lib:       A vunit Library
        file_list: A FileList object
        manifest:  A Manifest object
        as_ref:    True when the library should be added as an external reference, else False
        vu:        The Vunit object

    Returns:
        The modified Library

    """
    if vu.get_simulator_name() == "ghdl":
        vhdl_standard = "2008"
    else:
        vhdl_standard = to_vunit_vhdl_standard(file_list.standard)
    # Allow empty entries, just skip
    if file_list.files is None:
        return lib
    for file in file_list.files:
        file = Path(file)
        full_file_path = manifest.get_source_dir(file_list.kind) / file
        if file.suffix in (".svh", ".vh"):
            # Bleh.  Headers need to be copied for macros to work but shouldn't be compiled
            # Just copy them manually to the preprocessed folder where it should be
            pp_path = Path(vu._preprocessed_path) / lib.name / file.name
            if not pp_path.parent.exists():
                pp_path.parent.mkdir(parents=True)
            pp_path.write_bytes(full_file_path.read_bytes())
            continue

        if as_ref and file_list.kind == "tb" and file.suffix == ".vhd":
            # This is a referenced external in tb library, find out if it's a testbench - we don't want those
            # Construct a source file object from the filename
            source_file: SourceFile = VHDLSourceFile(
                full_file_path,
                lib,
                vhdl_parser=vu._project._vhdl_parser,
                database=vu._project._database,
                vhdl_standard=vhdl_standard,
                no_parse=False,
            )
            # See if it's a testbench
            is_tb = False
            for design_unit in source_file.design_units:
                if design_unit.is_entity or design_unit.is_module:
                    if tb_filter is None or tb_filter(design_unit):
                        is_tb = True
                        break
            # Skip compilation if it is
            if is_tb:
                continue

        source_file = lib.add_source_file(full_file_path, vhdl_standard=vhdl_standard)
    return lib


def override_compile(vu, simulator):
    orig_compile = vu._compile

    def questa_create_load_function(self, test_suite_name, config, output_path):
        """
        Create the vunit_load TCL function that runs the vsim command and loads the design
        """

        set_generic_str = " ".join(
            (
                "-g/%s/%s=%s" % (config.entity_name, name, encode_generic_value(value))
                for name, value in config.generics.items()
            )
        )
        pli_str = " ".join(
            "-pli {%s}" % fix_path(name) for name in config.sim_options.get("pli", [])
        )

        if config.architecture_name is None:
            architecture_suffix = ""
        else:
            architecture_suffix = "(%s)" % config.architecture_name

        if config.sim_options.get("enable_coverage", False):
            coverage_file = str(Path(output_path) / "coverage.ucdb")
            self._coverage_files.add(coverage_file)
            coverage_save_cmd = (
                "coverage save -onexit -testname {%s} -assert -directive -cvg -codeAll {%s}"
                % (test_suite_name, fix_path(coverage_file))
            )
            coverage_args = "-coverage"
        else:
            coverage_save_cmd = ""
            coverage_args = ""

        vsim_flags = [
            "-wlf {%s}" % fix_path(str(Path(output_path) / "vsim.wlf")),
            "-quiet",
            "-t ps",
            # for correct handling of verilog fatal/finish
            "-onfinish stop",
            pli_str,
            set_generic_str,
            config.library_name
            + "."
            + config.entity_name
            + "_opt"
            + architecture_suffix,
            coverage_args,
            self._vsim_extra_args(config),
        ]

        # There is a known bug in modelsim that prevents the -modelsimini flag from accepting
        # a space in the path even with escaping, see issue #36
        if " " not in self._sim_cfg_file_name:
            vsim_flags.insert(0, "-modelsimini %s" % fix_path(self._sim_cfg_file_name))

        for library in self._libraries:
            vsim_flags += ["-L", library.name]

        vhdl_assert_stop_level_mapping = dict(warning=1, error=2, failure=3)

        tcl = """
proc vunit_load {{{{vsim_extra_args ""}}}} {{
    set vsim_failed [catch {{
        eval vsim ${{vsim_extra_args}} {{{vsim_flags}}}
    }}]

    if {{${{vsim_failed}}}} {{
       echo Command 'vsim ${{vsim_extra_args}} {vsim_flags}' failed
       echo Bad flag from vsim_extra_args?
       return true
    }}

    if {{[_vunit_source_init_files_after_load]}} {{
        return true
    }}

    global BreakOnAssertion
    set BreakOnAssertion {break_on_assert}

    global NumericStdNoWarnings
    set NumericStdNoWarnings {no_warnings}

    global StdArithNoWarnings
    set StdArithNoWarnings {no_warnings}

    {coverage_save_cmd}
    return false
}}
""".format(
            coverage_save_cmd=coverage_save_cmd,
            vsim_flags=" ".join(vsim_flags),
            break_on_assert=vhdl_assert_stop_level_mapping[
                config.vhdl_assert_stop_level
            ],
            no_warnings=1
            if config.sim_options.get("disable_ieee_warnings", False)
            else 0,
        )

        return tcl

    def questa_optimize_project(self, project, printer, target_files):
        print("Optimizing stuff")
        library_names = self._libraries
        libraries = " ".join([f"-L {lib.name}" for lib in self._libraries])
        opt_targets = [
            (
                [unit for unit in target_file.design_units if unit.is_entity][0].name,
                target_file.library.name,
            )
            for target_file in target_files
        ]
        opt_targets.append(("glbl", "xilinxcorelib_ver"))
        for entity, library in opt_targets:
            printer.write(f"Optimizing {entity}".ljust(50))
            command = (
                f"{str(Path(self._prefix) / 'vopt')} {entity} -o {entity}_opt"
                f" -modelsimini {self._sim_cfg_file_name}"
                f" -quiet"
                f" -work {library}"
                f" {libraries}"
                f" -suppress 8602"
                f" +acc"
            )
            if entity != "glbl":
                command += f" xilinxcorelib_ver.glbl"

            try:
                output = check_output(command)
                printer.write("passed", fg="gi")
                printer.write("\n")
            except subprocess.CalledProcessError as err:
                printer.write("failed", fg="ri")
                printer.write("\n")
                printer.write("=== Command used: ===\n%s\n" % (command))
                printer.write("\n")
                printer.write("=== Command output: ===\n%s\n" % err.output)

    def optimize_project(self, project, printer, target_files):
        if simulator == "qsim":
            return questa_optimize_project(self, project, printer, target_files)
        return True

    def custom_compile(self, simulator_if: SimulatorInterface):
        setattr(
            simulator_if,
            "optimize_project",
            types.MethodType(optimize_project, simulator_if),
        )
        if simulator == "qsim":
            override_instance_method(
                simulator_if,
                simulator_if._create_load_function,
                questa_create_load_function,
            )

        optimization_files = []
        target_files = self._get_testbench_files(simulator_if)
        for target_file in target_files:
            files_recompiled = self._project.get_minimal_file_set_in_compile_order(
                [target_file]
            )
            if files_recompiled:
                optimization_files.append(target_file)

        orig_compile(simulator_if)
        simulator_if.optimize_project(
            self._project,
            printer=self._printer,
            target_files=target_files,
        )

    override_instance_method(vu, vu._compile, custom_compile)


if __name__ == "__main__":
    main()
