#include <assert.h>
#include <byteswap.h>
#include <endian.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zlib.h>

#include "bnx2_fw_file.h"

struct fw_info {
  const uint32_t ver_major;
  const uint32_t ver_minor;
  const uint32_t ver_fix;

  const uint32_t start_addr;

  /* Text section. */
  const uint32_t text_addr;
  const uint32_t text_len;
  const uint32_t text_index;
  void *text;
  const void *gz_text;
  const uint32_t gz_text_len;

  /* Data section. */
  const uint32_t data_addr;
  const uint32_t data_len;
  const uint32_t data_index;
  const uint32_t *data;

  /* SBSS section. */
  const uint32_t sbss_addr;
  const uint32_t sbss_len;
  const uint32_t sbss_index;

  /* BSS section. */
  const uint32_t bss_addr;
  const uint32_t bss_len;
  const uint32_t bss_index;

  /* Read-only section. */
  const uint32_t rodata_addr;
  const uint32_t rodata_len;
  const uint32_t rodata_index;
  const uint32_t *rodata;
};

typedef uint8_t u8;
typedef uint32_t u32;

#include "bnx2_fw.h"
#include "bnx2_fw2.h"

#if __BYTE_ORDER == __LITTLE_ENDIAN
#define cpu_to_be32(x) bswap_32(x)
#elif __BYTE_ORDER == __BIG_ENDIAN
#define cpu_to_be32(x) (x)
#endif
#define le32_to_be32(x) bswap_32(x)

void set_firmware_image_part(struct bnx2_fw_file_section *s, const char *text, uint32_t addr, uint32_t len, uint32_t offset)
{
  printf("Setup %s segment. addr: %08x, len: %d, fileoffset: %u\n", text, addr, len, offset);
  s->addr = cpu_to_be32(addr);
  s->len = cpu_to_be32(len);
  s->offset = cpu_to_be32(offset);
}

void write_firmware_flat(int fd, struct bnx2_fw_file_section *out, const char *text, void *data, int len)
{
  off_t offset = lseek(fd, 0, SEEK_CUR);

  uint32_t buf[0x10000];
  struct z_stream_s strm;
  memset(&strm, 0, sizeof strm);

  strm.next_in = (void *)data;
  strm.avail_in = len;
  strm.next_out = (void *)buf;
  strm.avail_out = sizeof buf;

  int ret = inflateInit2(&strm, -MAX_WBITS);
  assert(ret == Z_OK);
  ret = inflate(&strm, Z_FINISH);
  assert(ret == Z_STREAM_END);
  unsigned int l = strm.total_out;

  printf("Write %s firmware. len: %d, fileoffset: %d\n", text, l, offset);

  out->len = cpu_to_be32(l);
  out->offset = cpu_to_be32(offset);

  inflateEnd(&strm);

  for (unsigned int j = 0; j < (l / 4); j++)
    buf[j] = le32_to_be32(buf[j]);
  write(fd, buf, l);
}

void write_firmware_image(int fd, struct bnx2_fw_file_entry *out, const char *text, struct fw_info *fw)
{
  off_t offset = lseek(fd, 0, SEEK_CUR);

  printf("Write %s firmware\n", text);

  out->start_addr = cpu_to_be32(fw->start_addr);

  set_firmware_image_part(&out->text, "text", fw->text_addr, fw->text_len, offset);

  uint32_t buf[0x10000];
  struct z_stream_s strm;
  memset(&strm, 0, sizeof strm);

  strm.next_in = (void *)fw->gz_text;
  strm.avail_in = fw->gz_text_len;
  strm.next_out = (void *)buf;
  strm.avail_out = sizeof buf;

  int ret = inflateInit2(&strm, -MAX_WBITS);
  assert(ret == Z_OK);
  ret = inflate(&strm, Z_FINISH);
  assert(ret == Z_STREAM_END);
  inflateEnd(&strm);

  for (unsigned int j = 0; j < (fw->text_len / 4); j++)
    buf[j] = le32_to_be32(buf[j]);
  offset += write(fd, buf, fw->text_len);

  if (fw->data_addr)
  {
    set_firmware_image_part(&out->data, "data", fw->data_addr, fw->data_len, offset);
    for (unsigned int j = 0; j < (fw->data_len / 4); j++)
      buf[j] = cpu_to_be32(fw->data[j]);
    offset += write(fd, buf, fw->data_len);
  }

  if (fw->sbss_len)
    set_firmware_image_part(&out->sbss, "sbss", fw->sbss_addr, fw->sbss_len, 0);

  if (fw->bss_len)
    set_firmware_image_part(&out->bss, "bss", fw->bss_addr, fw->bss_len, 0);

  if (fw->rodata_addr)
  {
    set_firmware_image_part(&out->rodata, "rodata", fw->rodata_addr, fw->rodata_len, offset);
    for (unsigned int j = 0; j < (fw->rodata_len / 4); j++)
      buf[j] = cpu_to_be32(fw->rodata[j]);
    offset += write(fd, buf, fw->rodata_len);
  }
}

void write_firmware(const char *filename, struct fw_info *com_fw, struct fw_info *cp_fw, struct fw_info *rxp_fw, struct fw_info *tpat_fw, struct fw_info *txp_fw, void *rv2p_proc1, int rv2p_proc1_len, void *rv2p_proc2, int rv2p_proc2_len)
{
  struct bnx2_fw_file out;
  memset(&out, 0, sizeof out);

  printf("Write firmware file: %s\n", filename);

  int fd = open(filename, O_WRONLY | O_CREAT, 0666);

  lseek(fd, sizeof out, SEEK_SET);

  write_firmware_image(fd, &out.com, "com", com_fw);
  write_firmware_image(fd, &out.cp, "cp", cp_fw);
  write_firmware_image(fd, &out.rxp, "rxp", rxp_fw);
  write_firmware_image(fd, &out.tpat, "tpat", tpat_fw);
  write_firmware_image(fd, &out.txp, "txp", txp_fw);
  write_firmware_flat(fd, &out.rv2p_proc1, "rv2p-proc1", rv2p_proc1, rv2p_proc1_len);
  write_firmware_flat(fd, &out.rv2p_proc2, "rv2p-proc2", rv2p_proc2, rv2p_proc2_len);

  lseek(fd, 0, SEEK_SET);

  write(fd, &out, sizeof out);

  close(fd);
}

