struct cpu_reg {
  unsigned int mode;
  unsigned int mode_value_halt;
  unsigned int mode_value_sstep;

  unsigned int state;
  unsigned int state_value_clear;

  unsigned int gpr0;
  unsigned int evmask;
  unsigned int pc;
  unsigned int inst;
  unsigned int bp;

  unsigned int spad_base;

  unsigned int mips_view_base;
};

#include "bnx2_fwcutter_2.6.27.h"
#include "bnx2_fwcutter.c"

int main()
{
  write_firmware("bnx2-06-4.1.1.fw",
      &bnx2_com_fw_06,
      &bnx2_cp_fw_06,
      &bnx2_rxp_fw_06,
      &bnx2_tpat_fw_06,
      &bnx2_txp_fw_06,
      bnx2_rv2p_proc1, sizeof bnx2_rv2p_proc1,
      bnx2_rv2p_proc2, sizeof bnx2_rv2p_proc2);
  write_firmware("bnx2-09-4.4.26.fw",
      &bnx2_com_fw_09,
      &bnx2_cp_fw_09,
      &bnx2_rxp_fw_09,
      &bnx2_tpat_fw_09,
      &bnx2_txp_fw_09,
      bnx2_xi_rv2p_proc1, sizeof bnx2_xi_rv2p_proc2,
      bnx2_xi_rv2p_proc2, sizeof bnx2_xi_rv2p_proc2);

  return EXIT_SUCCESS;
}

