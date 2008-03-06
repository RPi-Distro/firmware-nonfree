struct bnx2_fw_file_section {
  uint32_t addr;
  uint32_t len;
  uint32_t offset;
};

struct bnx2_fw_file_entry {
  uint32_t start_addr;
  struct bnx2_fw_file_section text;
  struct bnx2_fw_file_section data;
  struct bnx2_fw_file_section sbss;
  struct bnx2_fw_file_section bss;
  struct bnx2_fw_file_section rodata;
};

struct bnx2_fw_file {
  struct bnx2_fw_file_entry com;
  struct bnx2_fw_file_entry cp;
  struct bnx2_fw_file_entry rxp;
  struct bnx2_fw_file_entry tpat;
  struct bnx2_fw_file_entry txp;
  struct bnx2_fw_file_section rv2p_proc1;
  struct bnx2_fw_file_section rv2p_proc2;
};

