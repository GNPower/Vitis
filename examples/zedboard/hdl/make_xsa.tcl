# Generate a minimal ZedBoard hardware file (.xsa) for the example project.
#
# The design is a bare Zynq-7000 Processing System (no PL logic) with UART1
# enabled so the standalone BSP can support xil_printf.
#
# Run headless:
#   vivado -mode batch -source make_xsa.tcl -tclargs <output.xsa>

set xsa_out [lindex $argv 0]
if {$xsa_out eq ""} {
    set xsa_out "ZedBoard.xsa"
}
set xsa_out [file normalize $xsa_out]

set part   "xc7z020clg484-1"
set design "system"
set prj_dir [file join [file dirname $xsa_out] .vivado_zed]

file delete -force $prj_dir
create_project -force zed_base $prj_dir -part $part

create_bd_design $design

# Zynq-7000 PS. No version pin: Vivado resolves it automatically.
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps7_0

# Default PS config for the part (no board-file dependency), external DDR/FIXED_IO.
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "0" Master "Disable" Slave "Disable"} \
    [get_bd_cells ps7_0]

# This example has no PL logic. Disable the AXI GP master (otherwise its clock
# pin M_AXI_GP0_ACLK is left dangling and validate_bd_design fails), and enable
# UART1 (ZedBoard's console UART) so standalone stdin/stdout has a target.
set_property -dict [list \
    CONFIG.PCW_USE_M_AXI_GP0 {0} \
    CONFIG.PCW_UART1_PERIPHERAL_ENABLE {1} \
] [get_bd_cells ps7_0]

validate_bd_design
save_bd_design

set bd_file [get_files "$design.bd"]
generate_target all $bd_file

# Wrap the block design in an HDL top and make it the project top.
set wrapper [make_wrapper -files $bd_file -top -force]
add_files -norecurse $wrapper
set_property top "${design}_wrapper" [current_fileset]
update_compile_order -fileset sources_1

# Vitis 2024.1 platform creation reads the full hardware handoff (sysdef.xml),
# which only exists after synthesis and implementation. Run them (fast for a
# bare PS design), then export a fixed XSA including the bitstream.
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
open_run impl_1
write_hw_platform -fixed -include_bit -force -file $xsa_out
puts "make_xsa.tcl: wrote $xsa_out"
