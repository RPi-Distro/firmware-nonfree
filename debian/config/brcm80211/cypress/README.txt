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

Be aware that an update of the firmware-brcm80211 package may require that the
symbolic link be restored.

In an up-to-date Raspberry Pi OS install, you can switch between the two
variants by running the following command:

    sudo update-alternatives --config cyfmac43455-sdio.bin

This method will persist across firmware-brcm80211 updates.
