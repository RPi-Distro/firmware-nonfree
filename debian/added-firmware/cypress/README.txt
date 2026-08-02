The file cyfmac43455-sdio-minimal.bin is an alternative firmware that has been
tuned to maximise the number of clients in AP mode while still supporting STA
mode. The expected number of supported clients using this firmware is now 19.
To achieve this, a number of features have been removed:

* advanced roaming features (802.11k, 802.11v and 802.11r)
* dfsradar - allows an AP to operate in channels that may be used by radar
  systems
* obss-obssdump - ACS (Auto Channel Support)
* swdiv - antenna diversity (this is not relevant with only one antenna)

In order to use this firmware, the symbolic link ../brcm/brcmfmac43455-sdio.bin
should be modified to point to the -minimal version. Running from a shell with
its current working directory set to ../brcm:

    sudo ln -sf ./cypress/cyfmac43455-sdio-minimal.bin brcmfmac43455-sdio.bin

Another alternative firmware cyfmac43455-sdio-wpa3.bin is available that enables
long-term correct WPA3 function for both STA and AP mode. It is an unofficial
patched version based on a newer official firmware version released by the vendor:
BCM4345/6 wl0: Oct 28 2024 23:27:00 version 7.45.286 (be70ab3 CY) FWID 01-95efe7fa.
It is not needed if you plan running in WPA2 mode (but may improve stability anyway
given it's based on a newer version). More details of the fix it provides here:
https://github.com/raspberrypi/linux/issues/7528

In order to use this firmware, follow the same process as for the minimal version:

    sudo ln -sf ./cypress/cyfmac43455-sdio-wpa3.bin brcmfmac43455-sdio.bin

Be aware that an update of the firmware-brcm80211 package may require that the
symbolic link be restored.

In an up-to-date Raspberry Pi OS install, you can switch between the three
variants (standard, minimal and wpa3) by running the following command:

    sudo update-alternatives --config cyfmac43455-sdio.bin

This method will persist across firmware-brcm80211 updates.
