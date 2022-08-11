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

set component_path [lindex ${argv} 0]
set filelist [lindex ${argv} 1]

ipx::open_ipxact_file $component_path

source $filelist

foreach {path lib standard} $all_sources {
  ipx::add_file $path [ipx::get_file_groups xilinx_anylanguagesynthesis]
  if {[string compare $lib "N/A"] != 0} {
    set_property library_name $lib [ipx::get_files $path -of_objects [ipx::get_file_groups xilinx_anylanguagesynthesis -of_objects [ipx::current_core]]]

  }
  if {[string compare $standard "N/A"] != 0} {
    set_property type $standard [ipx::get_files $path -of_objects [ipx::get_file_groups xilinx_anylanguagesynthesis -of_objects [ipx::current_core]]]
  }
}
ipx::update_checksums [ipx::current_core]
ipx::save_core [ipx::current_core]
