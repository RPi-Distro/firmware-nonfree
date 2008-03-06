#include "bnx2_fwcutter.c"

int main()
{
  write_firmware("bnx2-06-4.0.5.fw",
      &bnx2_com_fw_06,
      &bnx2_cp_fw_06,
      &bnx2_rxp_fw_06,
      &bnx2_tpat_fw_06,
      &bnx2_txp_fw_06,
      bnx2_rv2p_proc1, sizeof bnx2_rv2p_proc1,
      bnx2_rv2p_proc2, sizeof bnx2_rv2p_proc2);
  write_firmware("bnx2-09-4.0.5.fw",
      &bnx2_com_fw_09,
      &bnx2_cp_fw_09,
      &bnx2_rxp_fw_09,
      &bnx2_tpat_fw_09,
      &bnx2_txp_fw_09,
      bnx2_xi_rv2p_proc1, sizeof bnx2_xi_rv2p_proc2,
      bnx2_xi_rv2p_proc2, sizeof bnx2_xi_rv2p_proc2);

  return EXIT_SUCCESS;
}

