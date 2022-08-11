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

set simulator_name [lindex $argv 0]
set simulator_exec_path [lindex $argv 1]
set output_path [lindex $argv 2]
set mode_32 [lindex $argv 3]

puts "simulator_name=${simulator_name}"
puts "simulator_exec_path=${simulator_exec_path}"
puts "output_path=${output_path}"
puts "mode_32=${mode_32}"

set_param general.maxThreads 8

# If you do not have System Verilog Assert license
# config_compile_simlib -reset
# config_compile_simlib -cfgopt {riviera.verilog.xpm:-sv2k12 -na sva}

set cmd [subst [join {
compile_simlib -force
    -language vhdl
    -language verilog
    -simulator ${simulator_name}
    -verbose
    -library unisim
    -library xpm
    -library simprim
    -family  zynq
    -no_ip_compile
    $mode_32
    -simulator_exec_path ${simulator_exec_path}
    -directory ${output_path}
} " "]]

puts "Running command ${cmd}"

eval "${cmd}"
