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

import csv
from os import environ
from pathlib import Path
import sys
import argparse
import re

BASE_DIR = Path(environ.get("BASE_DIR"))
OUTPUT_DIR = BASE_DIR / "scratch/vunit_out/"
TEST_STATUS_TXT = OUTPUT_DIR / "test_status.txt"
TEST_STATUS_CSV = OUTPUT_DIR / "test_status.csv"


def main():
    args = parse_args()
    if TEST_STATUS_CSV.exists() and not args.force:
        force = input(f"{TEST_STATUS_CSV} already exists.  Overwrite? (y/n)")
        if force.lower() not in ("y", "yes"):
            return
    rows = read_status_txt(TEST_STATUS_TXT)
    write_status_csv(TEST_STATUS_CSV, rows)


def read_status_txt(status_txt_path):
    rows = []
    with open(status_txt_path, "r") as txt_file:
        for line in txt_file:
            row = {}
            status, full_test = line.split(":")
            full_test = full_test.strip()
            row["status"] = status
            # Have to use regex split on period to handle case of test_param=0.9 etc
            # Match all periods not followed by a number
            portions = re.split(r"\.(?=[^0-9])", full_test)
            if len(portions) > 3:
                test = ".".join(portions[:-2]) + "." + portions[-1]
                row["test"] = test
                config_strings = portions[-2].split(",")
                for config_string in config_strings:
                    config, val = config_string.split("=")
                    row[config] = val
            else:
                row["test"] = full_test
            row["full_test"] = full_test
            rows.append(row)
    print(f"Read {len(rows)} tests from {status_txt_path}")
    return rows


def write_status_csv(status_csv_path, rows):
    with open(status_csv_path, "w+") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote to {status_csv_path}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a filterable CSV version of the most recent test results",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-f",
        "--force",
        help="Overwrites existing CSV without confirmation",
        action="store_true",
        default=False,
    )
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    main()
