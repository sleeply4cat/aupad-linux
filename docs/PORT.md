# CHUWI AuPad (Snapdragon 680, SM6225 "khaje") — mainline Linux / postmarketOS port

Engineering notes, oldest gotchas included. Start with the README. Paths like `build/` are relative to this repo.

## Starting point

- Upstream (v7.3) has **no SM6225 support**: no dtsi, TLMM, GCC, dispcc or gpucc driver.
  The only khaje reference is the Adreno entry in `drivers/gpu/drm/msm/adreno/a6xx_catalog.c`.
- pmOS `linux-postmarketos-qcom-sm6225` = TQMatvey/linux-sm6225, 6.1, last commit 2023-06,
  sm6125 hacks + `sm6225-lenovo-tb128fu.dts`, UFS not working. Use it only as a hint.
- Closest upstream SoC: **SM6115 (bengal)**. Stock DT says `qcom,khaje` / platform bengal.
  87 of the 111 node addresses in mainline `sm6115.dtsi` also exist in our stock DT (from the running device).
  Known real differences:
  - TLMM at **0x400000** (sm6115: 0x500000), gpio0..113, TZ-reserved 0-3, 14-17.
  - LPI pinctrl at 0xac40000 (sm6115: 0xa7c0000).
  - DSI PHY is `dsi-phy-v4.1` (7 nm); sm6115 uses 14 nm.
  - UFS PHY `ufs-phy-qmp-v4-khaje`; own gcc/dispcc/gpucc/rpmcc compatibles.
- Bootloader IDs for ABL DTB matching: `qcom,msm-id = <0x24a 0x10000 0x206 0x10000>`,
  `qcom,board-id = <0x10022 0x00>`.
- Debug UART SE4 @ 0x4a90000 is the same as sm6115 → `earlycon=qcom_geni,0x4a90000`.

## Milestones

1. **Serial shell. DONE 2026-10-30.** 8 CPUs, 7.4 GB, busybox shell on ttyMSM0.
2. **Clocks and pins. Mostly DONE.** `sm6225.dtsi` = `sm6115.dtsi` + overrides. Working: tlmm, RPM clocks and
   regulators, interconnect, cpufreq-hw (tables match Android), GENI UART, SMMU, SPMI + PM6125 PON, watchdog,
   CPU cooling, real `gcc-sm6225` (see Clocks).
3. **Storage and USB.** USB gadget DONE (HS only: ACM shell + NCM). QMP USB3/DP combo PHY not described.
   **UFS DONE 2026-10-30**: HS-G3 x2 rate B, about 600 MB/s read, 6 LUNs, 88 partitions, clock scaling works.
   Reads match Android's hashes. Write proven on recovery_b only (random marker read back, Android
   confirmed the hash). ICE/inline crypto not enabled yet (`SCSI_UFS_CRYPTO` off), `interconnects` not
   described on the UFS node. Mainline flashes itself through `build/fl.sh`.
4. **Display DONE 2026-10-30, test pattern confirmed by eye** (`tools/fbtest.py`, stride is 4864). `msm` DPU + DSI + 7 nm PHY + FT8201P
   panel run at 60 Hz, fb0 is `msmdrmfb` (see Display). Backlight confirmed by eye, touch mapped and confirmed with taps.
5. **Rootfs DONE 2026-10-30.** postmarketOS v26.06 (OpenRC, console only) boots from `pmos` (sda11, ext4, 4K
   blocks, 71.8 GB), SSH works, data survives. **Boots with no host** since U-Boot reads UFS: 10 s to network.
   Generic rootfs, no device/kernel packages.
6. **Battery readout DONE 2026-10-30.** CW2015 on i2c1 (`0-0062`), PM7250B on SPMI SID 2/3 with ADC and temp
   alarm. Status and current through a read-only driver; the PMIC still runs on bootloader settings (see Power).
7. **GPU DONE 2026-10-30.** A610 v2: GLES 3.2 (freedreno), Vulkan (Turnip), Weston, up to 1260 MHz, see GPU.
8. **Remoteprocs, Wi-Fi, Bluetooth, microSD DONE 2026-10-30.** See their sections.
9. **Phosh, buttons, auto-rotate DONE 2026-10-31.** See Desktop. Installed by hand, not packaged yet.
10. **Speakers, internal mic DONE 2026-10-31.** See Audio. Installed by hand, not packaged yet.
11. **LTE data, GPS, cluster idle, Bluetooth audio DONE 2026-10-31.** See their sections. Greeter fix and firmware installed by hand.
12. **Scripted OS rebuild, clean-tree kernel DONE 2026-10-31.** See Rootfs. Phosh, firmware and configs install from `build/pmos-install.sh`, not packaged yet.
13. **Rear camera raw capture and libcamera DONE 2026-10-31.** See Camera. Focus motor and image tuning open, front camera parked until its ribbon is checked.
14. Then: boot hang, PM7250B charger, suspend, USB3.

## Next steps (in order)

1. Boot hang: measure, isolate, fix. See that section.
2. Device, kernel and firmware packages for pmaports. Firmware comes from your own device. U-Boot expects `/boot/boot.img` on `pmos`, so the
   installer's layout needs adapting.
3. PM7250B charger control: raising the input limit above 500 mA, behaviour from a low battery. Status readout is done, see Power.
4. Suspend: whole-chip sleep first, see Suspend and power. Audio leftovers: headphones and headset mic once the jack ribbon is back.
5. Boot counter falling back to `/boot/boot.old`, so a hanging kernel on disk recovers without the UART.
6. USB3 PHY, ICE, UFS interconnect votes, MX vote for the GPU.
7. Clean up for upstreaming: real bindings, no stub in the chain.
8. Open: PMU root cause (see Stability gotchas); kexec early hang (replaced by U-Boot).

To go back to Android: run `build/boot-bcbclr.img`, then restore your own backup of recovery_b.

## Unlocking: vbmeta

The tablet is unlocked by a two-byte `devinfo` edit (bytes 13 and 14, 0 to 1) plus a `vbmeta` with flags 0x3, not the usual `fastboot flashing unlock`. ABL logs `VB: RWDeviceState: Succeed using devinfo!` and `Device is unlocked, Skipping boot verification` on every boot. Only the two together are known to work, neither was tested alone. The procedure is widely known, but the right image depends on the tablet's state and stock OS version, and `vbmeta_a` and `vbmeta_b` can be
different builds, so they aren't interchangeable. Patch the image from the running slot, and back up everything first. `adb reboot edl` gets you into EDL as long as Android runs.
A wrong `vbmeta` on the dev tablet gave a ramdump on every boot, cause never pinned down. adb is gone then, and only a magic cable, which forces EDL, got it back.

## Rootfs (2026-10-30)

The rootfs isn't built with pmbootstrap yet. The host only packs files, and the tablet finishes the install itself:

1. `build/mkrootfs.sh` packs Alpine 3.24 minirootfs + signed apk cache (`build/pmos/cache`, repos `build/pmos/repos`,
   keys `build/pmos/keys`) + `deviceinfo` into 1 GB `build/pmos/rootfs.img`. Package list is at the top of the script.
2. `build/ub.sh build/boot-root0.img 10`, then `build/flr.sh`: pushes to port 5556, `/bin/flashroot` writes only
   the partition named `pmos` and reads it back. **This wipes the rootfs.** Push within 45 s of boot.
3. `build/ub.sh build/boot-stage2.img 60`: `test=stage2` runs `apk add --no-network` with scripts, configures
   the system, grows the filesystem. Rerunnable.
4. `build/ub.sh build/boot-pmos.img 25`: `root=pmos`, the initramfs does the gadget, then switch_root.
5. `build/pmos-install.sh` on the running base system: packages from `build/pmos/world`, then `build/pmos/overlay.tar.gz`, the user, ownership and services. About 6 minutes through `tools/usbproxy.py`; set the clock first, the fresh system's date breaks TLS.

`build/mkoverlay.py` makes the overlay from a rootfs backup of a tablet that is already set up, `tar` streamed over ssh (BusyBox tar: `-X`, `-T`, no `--one-file-system`). The overlay is per-device and isn't in this repo: it holds stock firmware, the modem's rmtfs files, Wi-Fi and Bluetooth keys and the user's password hash. Never publish one. The first install has to follow the sections below by hand. `/home/user` starts empty.

The pmOS signing key came from the `postmarketos-keys` package on the mirror (trust on first use; it does verify
the index signature, not checked against a second source). Only local-install, no network on the tablet: new
packages mean adding them to `PKGS` and rerunning, or copying apks over.

Access: `ssh root@172.16.42.1` (your public key from `build/tests/authorized_keys`), UART and ttyGS0 are passwordless root
shells. tty1 asks for login and root has no password, which is moot without a keyboard.

- `unudhcpd` must run or NetworkManager drops the interface, link-local included, after 45 s without a lease. It
  starts from `/etc/local.d/flash.start`; the OpenRC service needs `net`, and `networking` fails here. No router or
  DNS offered. The initramfs has no DHCP server, so long test kernels lose USB networking (UART still works).
- `ub.sh` reboots a running pmOS with `rb recovery` on the UART: fast, but skips shutdown, so swclock isn't saved.
  Use `ssh ... reboot` to keep the clock.
- RTC (`rtc-pm8xxx`) reads, but holds time since power-on and isn't set; `swclock` restores the last shutdown time.
- `build/fl.sh` replaces recovery_b. Use it only with a stub + U-Boot image (`build/boot-ub.img`), never a kernel.
- Modules: `build/mods.sh` installs this build's stripped modules (93 MB) on running pmOS; run it before `kup.sh`,
  from the same build. They aren't in `rootfs.img`, so rerun it after reflashing the rootfs.
- `make Image modules dtb` stops at a DTB error and silently leaves modules unbuilt; check the output.
- `modules_install` ships stale `.ko`s when the tree turned `-dirty` after the modules were built: the Image
  rebuilds, `.ko`s don't, and vermagic misses `-dirty` (`Exec format error`, black screen with backlight —
  DRM is modular). `touch` the `.o`s and run `make modules` again before installing.


## Remoteprocs (2026-10-30)

ADSP, CDSP and modem boot through PAS from the stock firmware. The sm6115 nodes fit as they are.

- Rootfs setup is manual, not in `mkrootfs.sh`. Packages: `rmtfs pd-mapper tqftpserv qrtr` plus `-openrc`. Services `pd-mapper
  tqftpserv rmtfs` in `default`, and `rc_need="pd-mapper tqftpserv"` in `/etc/conf.d/rmtfs`, because `-s` makes rmtfs start the modem.
- Firmware in `/lib/firmware/qcom/sm6225/aupad/`: stock `modem.* adsp.* cdsp.* *.jsn modem_pr wlanmdsp.mbn qdsp6m.qdb`.
- EFS: rmtfs runs from files in `/var/lib/rmtfs` (`modem_fs1`, `modem_fs2`, `modem_fsg`, `modem_fsc`, copies of the stock partitions), so the
  real `modemst1/2` are never written. The path is `<dir>/modem_fs1`, not `<dir>/boot/...`. A missing file crashes the modem with
  `rmts_get_buffer api failed`.
- **QRTR race, fixed in `net/qrtr/ns.c`, upstream candidate.** The modem's HELLO can reach the name service before our own HELLO went out.
  Sending then gives -EAGAIN (`hello_sent` false), `announce_servers()` gave up, the modem never heard about rmtfs and sat at 2 services.
  The only sign was `failed to announce new service`. It now retries for up to 1 s.
- Modem crash recovery is not clean: after `stop`/`start` or a crash, it may need a reboot.
- Kernel PD mapper prints `PDM: no support for the platform`; the userspace `pd-mapper` does the job.
- Not done: fastrpc CMA.

## Wi-Fi (2026-10-30)

WCN3950 on the modem (`qcom,wcn3990-wifi`, ath10k_snoc, chip_id 0x120, WLAN.HL.3.2.4). **Works:** connected from Phosh's settings on 5 GHz at
-52 dBm, with traffic. Scan finds both bands. Throughput and long runs not measured.

- `/lib/firmware/ath10k/WCN3990/hw1.0/aupad/`: `firmware-5.bin` from linux-firmware `qcm2290/` (feature flags only), `board.bin` = stock
  `bdwlan.bin`, the one Android loads. DT has `firmware-name = "aupad"`. A real `board-2.bin` is still to do.
- Don't rmmod/modprobe ath10k_snoc to retry: `host capability request rejected: 90`. Reboot instead.
- The chip returns no MAC, and Android randomises too. `/etc/udev/rules.d/70-wlan-mac.rules` pins a generated locally administered one.
- NetworkManager owns Wi-Fi under Phosh, and `usb0` is unmanaged. `build/pmos/wifi-join` is only for a console-only rootfs.

## Bluetooth (2026-10-30)

Pairing and A2DP audio work, tested with one headset, see Bluetooth audio. Calls over Bluetooth untested.

- The chip is **WCN3950**, not RB2's WCN3988: SOC 0x40070120, ROM 0x102, on uart3 (gpio 8-11), PMU `qcom,wcn3950-pmu`. WCN3988 settings ask for
  a nonexistent `apbtfw0a.tlv`. Firmware `qca/cmbtfw12.tlv` + `cmnv12.bin` from stock `vendor/bt_firmware`.
- Packages `bluez bluez-btmgmt dbus`. No BD address in the chip and none found in stock data, so hci0 stays unconfigured until
  `/etc/local.d/bt-addr.start` sets the generated `/etc/bluetooth/bdaddr` with `btmgmt public-addr`. Needs the `local` service.

## microSD (2026-10-30)

`sdhc_2`, card detect GPIO 88, L22 and L5, L7 always on as pad bias (no mainline consumer). SDR104, 73 MB/s read. Writing untested.
Card-removal polarity not verified: stock says ACTIVE_HIGH, and with the pull-up an empty slot may also read high.

## Buttons (2026-10-31)

`pon_pwrkey`, `pon_resin` (volume down), `gpio-keys` on PM6125 GPIO 5 (volume up). All work, and power blanks and wakes the panel.
Power-off works (`reboot: Power down`); with USB attached the PMIC starts the tablet again about 3 s later.

## Camera (2026-10-31)

Rear OV13B10 streams 2104x1560 SGRBG10 at 60 fps through csiphy0, csid0 and vfe0 rdi0. libcamera 0.7.1 lists it as `Internal back camera` and delivers RGB at about 15 fps with the default GPU software ISP or the CPU one. PipeWire exposes it as `Built-in Back Camera`, `pipewire-spa-libcamera` is installed, Snapshot takes photos. Checked on a real scene: a window view is recognisable, far objects look reasonably sharp, nearby ones blur. Colour has a pink-purple cast, no tuning file. libcamera at 2104x1560 returns a 2x centre crop, not the whole view: window bars 710 px apart against 355 in the raw binned frame, so it apparently runs the sensor at 4208x3120 and crops.

- **Sensor:** Android's `sensor_id 0xd42` at 0x6c is OV13B10 at 7-bit 0x36, chip ID 0x560d42. `ov13b10.c` was ACPI-only, it now has an OF match. CCI master 0, MCLK0 19.2 MHz on gpio20, reset gpio18 (active low), four lanes at 560 MHz. Rails on PM8008 (i2c 0x08/0x09 on the CW2015 bus, reset gpio26, irq gpio25): L1 1.2 V vdig, L3 2.8 V vana, L7 1.8 V vio, L5 2.8 V vaf.
- **CAMSS:** new `sm6225` resources, three CSIPHY, CSID and TFE. TFE 530 and CSID 530 match mainline's 340 drivers at every offset used, checked against the tables in stock `camera.ko` (symbols survive there: `cam_tfe_csid_530_*`, `tfe530_*`, `csiphy_2ph_v1_2_1_reg`, `cam_csid_ppi_100_reg_offset`). The CSIPHY is not qcm2290's: `lane_regs_sm6225` is generated from `csiphy_2ph_v1_2_1_reg`. A PPI bridge sits at 0x5cb3000, the driver writes 0x70 to its 0x60 for D-PHY. The value is read from the stock disassembly, its bits are not understood.
- **`gpll10` needs `PLL_FSM_LEGACY_MODE`.** Stock's `clk_trion_pll_configure` sets it for `SUPPORTS_FSM_LEGACY_MODE`, mainline's did not, and the PLL failed to lock. It is the only PLL the TFE clock needs. Fixed in `clk-alpha-pll.c`: upstream candidate, and `gcc-sm6375.c` carries the same flag, so it changes behaviour there too.
- **Focus motor:** DW9714 (stock module data says `dw9714v`) at 0x0c on CCI master 0, `dongwoon,dw9714`, L5 as vcc, gpio108 is its power-down line, active low. It only answers with L7 on, so `ldo7` is always-on: assumed to be the CCI pull-ups, not measured. `focus_absolute` 0..1023 moves the lens: on a far scene sharpness is flat at 0-200 and worse above, so about 200 steps are a dead zone and rest is near infinity. The control only holds while the subdev stays open. Nothing drives autofocus.
- **Front camera (2026-11-13): GC5035 works, and it was at 0x37 all along.** The design sensor from the `cw_gc5035` tuning streams through CCI master 1, csiphy2, csid2 and vfe2 rdi0: 2592x1944 SGRBG10 at 29 fps and 1296x972 (2x2 binning) at 24 fps, checked on a real scene at both sizes. libcamera lists it with `camera_orientation` Front (from the DT `orientation`), `cam -l` shows both cameras. MCLK2 runs at 19.2 MHz, not the 24 MHz the stock tables assume. In-app use confirmed by the author: the camera works, orientation correct.
	- The sensor answers at 7-bit **0x37**. Every earlier scan (ours and Android's) missed it: 0x37 is inside the SMBus reserved block 0x30-0x37 that `i2cdetect` skips, and the manual scans probed arbitrary addresses instead. Found by binding the driver to all 112 addresses and raw-reading reg 0xf0 while the driver's own power sequence held the rails on (0x3550 = 0x5035 word-swapped). No driver existed in mainline: the port is the LKML v2 series by Nicola Fiorillo (2026-10-12, tested on the Chuwi Hi10 X1 with the same front camera), patches 0035-0037, plus 0038 (7.3.1 API: pad ops without `v4l2_subdev_client_info`; `galaxycore,gc5035` OF match, same pattern as `gc08a3`; `i2c_device_id` for name-instantiated clients). The driver hard-requires the 19.2 MHz xclk (422.4 MHz link full, 175.2 MHz binned).
	- DT: `camera@37` under `cci_i2c1` (patch 0039), `dovdd` = ldo7 `cam_vio`, `avdd` = ldo6 `cam_vana_front`, `dvdd` = ldo2 `cam_vdig_front`, reset gpio24 active low, powerdown gpio70 active low, `cam_mclk2_default` on gpio27, endpoint 2 lanes → csiphy2, both link frequencies listed.
	- Ops notes: the CCI bus numbers still shuffle between boots (front was i2c-3, then i2c-0; the entity name `gc5035 N-0037` follows), pick nodes by name. After a failed STREAMON ("Link has been severed", "select timeout") the sensor can stay marked streaming and every retry WARNs in `call_s_stream` and delivers no frames until unbind+bind resets it. libcamera (Snapshot/WirePlumber) grabs cameras on startup and media-ctl then refuses format/link changes with EBUSY: stop them first. The binned output has a dot-matrix texture from the vendor binning combining Bayer lines — the full-res mode is the clean one for stills.
- **Android tuning:** the board's tuning binaries are in the vendor partition, `lib64/camera/com.qti.tuned.chuwi_ov13b10.bin`, with `com.qti.sensormodule.ov13b10.bin` beside it for power, modes and the motor name. A `cw_gc5035` tuning shows the design has a GC5035 front camera. They are proprietary, so neither the files nor numbers from them are in this repo.
- **Colour:** rendered on the host from raw with measured white balance and the 5700 K matrix, a window view is neutral, so the matrices and the sensor data are good. Live, they don't work: libcamera's AWB counts clipped pixels (R gain 1.92 against 2.14 measured) and the matrix amplifies the error, giving green frames with pink sky. A/B on one scene: R/G 0.79 with `Ccm`, 0.91 without, and clearly better by eye. So `build/pmos/camera/ov13b10.yaml` has `BlackLevel` 4096 and no `Ccm`. No colour matrices are published here.
- **Rotation:** the DT says `rotation = <270>`, not stock's 90. Snapshot writes EXIF from it, and with 90 the sky came out at the bottom. The real image needs 90 degrees clockwise. Megapixels has its own `Rotate: 270`. The 270 build boots and reports it, but a photo from it hasn't been checked yet.
- **Megapixels 2.1:** `build/pmos/camera/`: `chuwi,aupad.conf` and the `/usr/local/bin/megapixels` wrapper. It also needs a DNG profile, `chuwi,aupad,Rear.dcp` (the sensor name is case-sensitive), which is not in this repo. The wrapper which starts it inside the config directory with `GSK_RENDERER=gl`. Preview draws upright, in full view, with ISO, exposure and focus controls. **It blinks red and green.** Bugs read from the 2.1.0 source:
  - `src/process_pipeline.c`, AWB: applies the full correction from statistics that lag the gains, so it oscillates. R/G flips 0.65 to 1.55 even with an identity matrix. Needs damping.
  - `src/dcp.c`: `for (const char *fmt = paths[0]; fmt; fmt++)` walks characters instead of strings, so it ends on some `/` string in rodata and prints `Found calibration file at /`. Only a suffix `%s,%s.dcp` relative to the working directory matches, hence the wrapper.
  - `src/io_pipeline.c`, preview mode: integer division and `score = 0` leave no mode scoring above 0, so preview falls back to 4208x3120 and drops about two frames in three.
  - `gles2_debayer_set_shading`: the order only works for mild matrices, so the profile's ForwardMatrix makes the product identity and is not a true ForwardMatrix.
  **The port carries no app patches.** So Megapixels stays on the stock package and keeps blinking. Camera (Snapshot) is the camera app. Dropping the 13 MP mode doesn't help: no frame drops, but R/G 0.10 to 0.35. Saved Megapixels photos are unchecked.
- **libcamera:** needs `CONFIG_DMABUF_HEAPS`, `DMABUF_HEAPS_SYSTEM`, `UDMABUF`. Leave `DMABUF_HEAPS_CMA` off: libcamera picks the small CMA heap and fails to allocate. `build/pmos/camera/62-aupad-camera.rules` opens the heap to group video.
- **Keep `CONFIG_DMABUF_DEBUG` off.** With it, `dma_buf_map_attachment` gives importers a scatterlist with `length` 0 and no pages, on purpose, while `msm_iommu_pagetable_map` walks `sg->length` and `sg_phys()`. So every buffer imported from another driver mapped nothing: `len=c92000 sgsum=0 nents=23/23`. Symptoms were GPU translation faults from TP, `__arm_lpae_unmap` warnings from `msm_gem_close`, Snapshot taking photos with a dead preview, `cam` stuck in GPU mode, and enough warnings on the UART to take the tablet down. It is on by default with `DEBUG_KERNEL`. The msm side is a genuine upstream problem: this only hides it.
- **No libcamera gain helper for this sensor:** metadata reports `AnalogueGain = 128`, the raw 1x code. AGC only moves exposure, so dim scenes stay dim.
- **Snapshot:** fills the screen with a centre crop, and has no manual controls.
- **Not done:** PIX path; binding docs (`ovti,ov13b10`, `qcom,sm6225-camss`, `qcom,sm6225-cci`); `vdd-l*-supply` on PM8008, S6 and S7 aren't described because a `regulator-min-microvolt` there would make RPM set them.
- **I2C bus numbers change between boots** (CCI was 0/2 on one boot, 1/2 on another, and the touch bus moved). Pick buses by name.

Test: `build/cam.sh [secs]` installs modules beside the running ones and RAM-boots. `build/pmos/camgrab W H N`, installed as `/usr/local/bin/camgrab`, captures raw to `/tmp/f.raw`, `CTRL=` passes sensor controls. Every `peek` argument is an address, so a count reads a real address: 16 reset the tablet. The front camera streams the same way with `csiphy2`/`csid2`/`vfe2_rdi0`/`msm_vfe2_video0` and the `gc5035 N-0037` subdev (bus number N changes between boots).

## Sensors and rotation (2026-10-31)

Accelerometer QMI8658, 0x6B on an ADSP-side I2C bus, so there is no plain IIO device. Auto-rotate works.

- `hexagonrpcd-adsp-sensorspd` plus Alpine's iio-sensor-proxy, which has SSC support. `/etc/conf.d/hexagonrpcd-adsp-sensorspd` sets
  `hexagonrpcd_fw_dir` and `rc_need="rmtfs"`.
- Served tree `/usr/share/qcom/sm6225/chuwi/aupad/`, owned by `fastrpc`: `dsp/{adsp,cdsp}` (vendor/dsp), `sensors/config`
  (vendor/etc/sensors/config), `sensors/sns_reg.conf` (vendor/etc/sensors/sns_reg_config), `sensors/registry` (`/sensors/registry/registry` in
  `persist`). Don't mirror Android's paths: a wrong layout crashes the ADSP in a loop with `sns_registry_sensor.c:154 SNS_RC_SUCCESS == rc`.
- `/etc/udev/rules.d/61-aupad-accel.rules` sets `ACCEL_MOUNT_MATRIX="-1, 0, 0; 0, -1, 0; 0, 0, 1"` on `fastrpc-adsp`, the node the SSC driver
  reads it from. Without it every orientation is 180 degrees off.
- Stock also lists stk3x1x light, ist8306 compass and bu52053nvx hall; iio-sensor-proxy shows none of them. Gyro not used.
- Open, dropped for now: booted flat, the picture is upside down. Proxy stays `undefined`, so Phosh keeps `rotate = 180` from `phoc.ini`; one later
  reading showed transform 0. `phoc.ini` may be the wrong way round for the current mount matrix. Restarting the proxy leaves Phosh unclaimed until reboot.

## Mobile data (2026-10-31)

LTE data works with the stock pmOS stack: ModemManager and NetworkManager, nothing custom. Registered on LTE, ping through `qmapmux0.0` at about 45 ms, and
it comes back by itself after a reboot. Speed not measured. Calls and SMS not tried.

- IPA is v4.2 (stock `qcom,ipa-hw-ver = <0x10>`), the same as SC7180, so no driver change. Node from `agatti.dtsi` (same addresses, IRQs, SID 0x140, RPM clock), compatible
  `qcom,sm6225-ipa`, `qcom,sc7180-ipa`, with a new `sram` node: agatti has none and the driver would fall back to SC7180's IMEM address. Stock has IMEM at `0xc123000`, size `0x2000`.
- AP loads the GSI firmware, PAS 15: stock `ipa_fws.mdt`, `.b00`-`.b04` in `/lib/firmware/qcom/sm6225/aupad/`. It is relocatable, `pil_ipa_fw_mem` holds it. Not `scuba_ipa_fws`.
- DSDS firmware doesn't activate the USIM itself: until something provisions it, `uim-get-card-status` shows `Primary GW: session doesn't exist`, the app stays `detected` and
  the modem searches forever. ModemManager does this, but it only takes the modem once `rmnet_ipa0` exists. Before that it says `No modems were found`.
- `no-atr-received` in a slot just means no SIM there. Power off to insert one.
- `sim-missing` from ModemManager doesn't prove there is no card: it's also what it reports while `Primary GW` has no session. Taking the SIM out and back in with the tablet on ended there (seen once): ModemManager recreates the modem after the SIM switch event, the app stays `detected` and nothing activates it; waited 2 minutes. A boot with the card in comes up by itself. Check with `qmicli -d qrtr://0 --device-open-proxy --uim-get-card-status`; `--uim-change-provisioning-session=slot=1,activate=yes,session-type=primary-gw-provisioning,aid=<USIM AID>` followed by `killall ModemManager` brings it back.
- `nmcli c add type gsm ifname '*' con-name mobile apn internet ipv6.method ignore`, added by hand, is per-operator. Wi-Fi keeps the default route, metric 600 against 20700.
- `rc-status` shows modemmanager `failed` while it works. Cosmetic: D-Bus activation starts it first, the service's own copy can't take the bus name, exits and respawns until
  supervise-daemon gives up. `rc-service restart` doesn't touch the D-Bus copy: use `killall ModemManager`.
- No SIM gives ModemManager state `failed`, reason `sim-missing`, and NetworkManager `unavailable`. That is normal, not a fault.
- Logged once at IPA setup: `unexpected init_completed response`, the uC finished before `uc_powered` was set, so `uc_loaded` stays false. Data works, but look here if
  modem restart or module removal misbehaves.


## GPS (2026-10-31)

Works through ModemManager, no kernel changes and no custom parts. Geoclue's stock `geoclue.conf` has `[modem-gps]` enabled.

- `mmcli -m any --location-enable-gps-nmea --location-enable-gps-raw`, then `--location-get`. Fix in 14 s when the modem has recent satellite data.
- Cold, before ModemManager had the modem: first fix after 3 min 10 s, 19 m uncertainty, standalone, no SIM. It dropped after 4 s; not seen again, but no long run since.
- Confirmed by the user on the tablet, 2026-10-31.


## Suspend and power (2026-10-31)

Running: schedutil on both clusters, `psci_idle` CPU power collapse, GPU and UFS devfreq. `current_now` on `cw2015-battery` is the measured battery current, so savings can now be measured (see Power).

s2idle (`rtcwake -d rtc0 -m freeze -s 15`, `qcom_stats` loaded) completes only with both workarounds, and stays disabled in elogind until the items below are done:

- **UART:** default settings freeze the SoC while devices suspend, silent, `RST_STAT 03`, 2 of 2 runs. `echo N > /sys/module/printk/parameters/console_suspend` avoids it, 2 of 2. Same family
  as "unbinding the UART panics", and the same reset signature as the boot hang; a link between them isn't proven.
- **ADSP:** with sensors running, resume gives `fatal error received: err_qdi.c:1045:EX:sensor_process: frpc_dsp`, 1 of 1. Stopping `iio-sensor-proxy` and `hexagonrpcd-adsp-sensorspd` first avoids it, 1 of 1.
  Probably the frozen hexagonrpcd, not proven.
- **ADSP recovery panics:** audio teardown, then SError in `swrm_wait_for_wr_fifo_done` from `pm_runtime_work`, 9 s later. Separate bug: any ADSP crash can kill the system.
- **USB doesn't come back:** `dwc3: failed to enable ep0out`, UDC `not attached`, ssh gone until reboot. Results then only over the serial console. Wi-Fi rejoins by itself.
- **Cluster idle, fixed.** Firmware rejected SM6115's parameters, so genpd showed Usage 0 and millions Rejected (that counter means PSCI failed, not a governor decision). sm6225.dtsi now
  uses stock's one state per cluster, `0x41000043`, plus a parent domain with `cci-pc`, `0x42000343`. `cci-ret` `0x42000043` is in stock's DT too but returns INVALID_PARAMETERS (-22): left out.
  Occasional -95 and -1 are normal, a wake arrived during entry. Six reboots clean, then 10 minutes up, no dumps. Too few to say anything about the boot hang.
- **What wakes a suspend:** with services and radios up, CCI got 1204 entries in 30 s, with 19 ms of residency. With greetd, sensors and ModemManager stopped, `rfkill block all` and the gadget detached: 1 entry in 60 s.
- **`vlow` and `vmin` still 0** even then, Client Votes unchanged at `0x83818581`. RPM isn't allowing it. Next suspects: `clk_ignore_unused`, `pd_ignore_unused`, USB attached. Decoding the votes would help.
- Detaching the gadget avoids `dwc3 ... failed to suspend: -11` on a second suspend, but reattaching still gives `failed to enable ep0out`. `HS-PHY not in L2` comes first.
- After resume with `console_suspend=N`, the UART loses incoming characters (`input overrun`, `Unbalanced pm_runtime_enable`). TX is fine. Type slowly to get a command through.
- A failed `rtcwake` says `write error`; check `/sys/power/suspend_stats`, and don't trust counters from such a run.
- Only the RTC wake is tested; power button isn't. `clk_ignore_unused pd_ignore_unused` still on the cmdline, removal untested.

### Power fixes landed (2026-11-13; hardware-tested same day)

Full analysis and staged plan: `audit/Энергосбережение_исследование.md`. Landed this session:

- **0040 `dwc3-qcom`: UTMI PIPE clock restored on resume.** Backport of the upstream fix (Falezza, 2026-10-27, patchew 20261027-dwc3-utmi-resume): the glue only programmed QSCRATCH GENERAL_CFG in probe, CX collapse during s2idle drops it, and the gadget dies with `failed to enable ep0out` — our exact symptom, including the preceding `HS-PHY not in L2`.
- **0044 `dwc3-qcom-legacy`: the same fix, mirrored.** First hardware run showed the AuPad's `usb@4ef8800` binds **dwc3-qcom-legacy** (`"qcom,sm6115-dwc3", "qcom,dwc3"`), which 0040 doesn't touch — the upstream author knowingly left the legacy glue alone. Hardware result after 0044: `failed to enable ep0out` is gone from resume, the controller survives, but the gadget link still stays `not attached` after resume and needs `unbind`/`bind` of `4ef8800.usb` to reconnect (then it's `configured` and ssh works). Suspect: with EUD enabled our femto-PHY patch 0029 keeps the PHY out of dwc3's hands; upstream tested with EUD off. Open.
- **0041 RPM master stats.** Five v2 structs in MSG RAM at `0x45f0150` (stride `0x1000`: APSS/MPSS/ADSP/CDSP/TZ) taken from the stock khaje DTB (`vendor_boot` blob 0), wired to `qcom,rpm-master-stats`; `CONFIG_QCOM_RPM_MASTER_STATS=m` added. `CONFIG_QCOM_PDC`/`RESET_QCOM_PDC` dropped — PDC doesn't exist on this RPM-generation die.
  Hardware: works after `modprobe rpm_master_stats` (load it after boot; the debugfs dir appears then). **APSS shows `Shutdown count` growing (4 after one 45 s suspend) but `XO shutdown count` stays 0** — the cluster collapses, yet XO never turns off: the remaining vlow/vmin blocker is on the APSS side (votes/clocks), not ADSP (XO count 3043) or the modem.
- **0042 MPM.** khaje is the qcm2290 die family, so the node mirrors in-tree qcm2290 (agatti): vMPM slice at MSG RAM `0x1b8` (matches the stock DTB's `mpm@45f01b8`), APCS mbox channel 1, 96 pins, pin map 2→275 (TSENS0), 5→296 (SoundWire), 12→422 (DWC3 SS), 24→79 (SoundWire wake), 86→183 (SPMI), 90→260 (QUSB2). The spmi-arb and tsens0-uplow interrupts are routed through it.
  Hardware: probe clean, `qcom_mpm` on GIC 229, tsens0 through the `mpm` domain. **RTC wake through MPM measured exact: sysfs-armed `wakealarm` +45 s woke the system after exactly 45 s of s2idle.** Power-button wake not yet tried by hand.
- **0043 wake sources.** `wakeup-source` on `pon_pwrkey` and the USB gadget; the duplicated `&pon_pwrkey`/`&pon_resin` blocks removed.
- **elogind hook.** `build/pmos/aupad-system-sleep.sh` (installed by mkrootfs.sh to `/etc/elogind/system-sleep/aupad.sh`): stops `iio-sensor-proxy` and `hexagonrpcd-adsp-sensorspd` before suspend, restarts after — formalises the ADSP workaround above.

Hardware findings of the same session:

- **45 s s2idle with the flags on:** completes cleanly, `vlow`/`vmin` still 0, but **Client Votes drop from `0x87858785` (idle) to `0x81` while asleep** — nearly everything unvotes; two bits stay. With APSS XO at 0 the leftover suspects are the flags' own clock/pd votes and the attached cable.
- **rtcwake is the wrong tool here:** `-m no` returns immediately by design ("don't suspend, just set the alarm"), and its ioctl-arming path produced a 6.3M `pm8xxx_rtc_alarm` IRQ storm that woke freezes in ~240 ms (and 3 s on the old kernel). Sysfs arming (`echo $((E+N)) > /sys/class/rtc/rtc0/wakealarm`) is exact: 1 IRQ after N seconds, no storm; `echo 0 > wakealarm` clears any leftover. Use sysfs + `echo freeze > /sys/power/state` (from `nohup`, the ssh session dies with the gadget) for suspend measurements.
- **Dropping `clk_ignore_unused pd_ignore_unused` is not safe yet:** it boots, but audio fails at boot (`snd-sc8280xp: can't create pcm MultiMedia1 Playback :-110`, the audio PD doesn't come up), and the first suspend leaves the GPU locked up (msm hangcheck spam, UI frozen, gadget `configured` but the host never creates the NCM interface). Both flags restored; they stay until the audio-PD bring-up and the GPU resume path are understood (stage D of the plan).

Remaining from the test order: ~~suspend with the cable out~~, ~~power-button wake by hand~~ — both done later that night:

- **Cable-out cycle** (60 s freeze, flags on): RTC alarm woke it after 62 s; `vlow`/`vmin` **still 0 without the cable** — USB is not the vlow blocker; the APSS-side suspects stand. Post-wake Client Votes `0x87838783` vs idle `0x87858785` (the cable's own bit drops out). Replugging after resume does not bring the gadget link back — same unbind/bind needed.
- **Power-button wake**: froze, pressed the button after ~16 s — `pm8941_pwrkey` IRQ 0→1 and `PM: suspend exit` at 16 s, well before the +300 s fallback alarm. Button wake through PON→SPMI→MPM→GIC works.

Still open: decoding the leftover vote bits, audio-PD bring-up and GPU resume (needed before dropping the flags). The gadget-link question was closed the next day — below.


### Power follow-up (2026-11-14: EUD-off experiment; user suspend works)

**The EUD hypothesis is disproved — EUD is not the link blocker, it is what keeps the PHY alive.**

- The stub enables the EUD on every boot exactly like stock `eud.ko` (`stub/main.c`): a TCSR write over the SCM, `CTLOUT (0x1611014) = 1`, and **`mode_mgr2 (0x1612000) = 1` over the SCM**. That register survives warm reboots, crash reboots and "power off"; only an SCM write turns it off. A plain Linux write to `0x1612000` is a non-secure access to a secure register and **panics the kernel on the spot** — confirmed twice (once from `/dev/mem` python on a live link, once from an initramfs poke; the second made a `panic=10` boot loop, recovered without hands: eudlog attached, space-spam stopped U-Boot's autoboot over the EUD COM, `run fastboot`, `fastboot boot` a good image, restore `/boot/boot.img` from `boot.old`). The old `poke 0x1611014 0` recipe only flips the stub's warm/cold detection (`eud_was_on`), not the mux.
- `build/tests/eudoff.c` (out-of-tree module, `qcom_scm_io_writel(mode_mgr2, 0)` + `CTLOUT = 0`): the sanctioned runtime disable. Works: the EUD hub leaves the host bus, the gadget re-enumerates direct, link `configured`, freeze on schedule, RTC-exact wake (`PM: suspend exit`, wlan re-associates) — **and the box dies within ~2 s of resume**, before the first UDC poll. With the PHY really powered down by `phy_exit`, its re-init hangs the system. So: with EUD on, suspend survives but the link needs a rebind; with EUD off, suspend doesn't survive resume at all. The femto-PHY power-cycle joins audio-PD and GPU-resume on the bring-up list; **EUD stays on**.
- **User suspend now works end to end** (stage H closed). What was wrong:
  - `/etc/elogind/sleep.conf.d/50-aupad-nosuspend.conf` (2026-10-31, "suspend is untested") — superseded by `build/pmos/aupad-sleep.conf`, installed by mkrootfs as `/etc/elogind/sleep.conf.d/50-aupad.conf` (`AllowSuspend=yes`; hibernation stays off).
  - **elogind calls system-sleep hooks with `("pre"|"post")` and the verb** — `post suspend`, never `post resume`. A `post/resume)` case matches nothing and silently does no work; caught by phase logging in `/var/log/aupad-sleep.log` (post "began" and "ended" in the same second).
  - The post phase rebinds `4ef8800.usb` unconditionally: a "configured" UDC can sit on a dead host-side link (observed: resume clean, wlan back, UDC `configured`, host sees no device). Each sysfs write goes through a child shell — an unbind write has taken a SIGBUS in the writing process once (el0 sync trace).
  - Measured full cycle: `pre` 1–2 s (services down) → freeze → RTC-exact wake → `post` 5 s (`rebind done, udc configured`) → SSH alive, ping gap only during sleep.

### Power day 3 (2026-11-15: votes decode, stock parity, the handoff test)

Full report chain: `audit/votes-20261114/` (README — method + day-2 table, BYTES.md —
byte decomposition, DOWNSTREAM-DECODE.md — the agent's research, misc backup).

- **Stock Android 15 (msm-5.15) is at full suspend parity with the port**: booted through
  the restored `qmmi` misc command (RAM-boot `boot-bcbclr.img`; `bcbclr.sh` now auto-reboots
  with `bcbreboot` on the cmdline). Measured with adb + Magisk su (`adb root` refused,
  production build): `qcom_sleep_stats` **vlow/vmin Count = 0**, `rpm_master_stats`
  **APSS xo_count = 0** (MPSS 0x39b), `mem_sleep=[s2idle]` — the "vlow blocker" is product
  behavior, not a port defect (stage D closed as N/A). Stock's own `echo mem > state`
  failed with `4e00000.ssusb EBUSY` while adb was active — our pmOS suspends with a live
  NCM gadget and RTC-wakes. Stock never writes the vlow votes block at all (0x0); ours
  does (0x81 in true sleep). Return path: push the misc backup, `su -c dd` it to
  `/dev/block/bootdevice/by-name/misc`, `adb reboot` — no EDL needed. EUD dies under
  Android (the stub doesn't run on the boot_b path and ABL/Android clear mode_mgr2) —
  adb only, no console.
- **Votes semantics** (no public table exists — the decode lives in the closed rpm_proc;
  Maulik Shah, QTI, on LKML for qcm2290): each byte of `Client Votes` is xo-clock votes
  of a subsystem (4-byte history; TZ covered by APSS); bit 7 is a validity marker, never
  a blocker; bits 0–2 accumulate as blockers. vlow == XO off SoC-wide; vmin adds rail
  minimization; entry needs all subsystems power-down + clean sleep votes + enough sleep
  time. Our 0x81 floor = one group (APSS side) holding an xo vote — the same signature
  the SM6115 Pro1-X port fixed (vmin 85% of sleep, 35–40 mA after their series).
- **0045 `clk: qcom: smd-rpm: skip the clock handoff votes on sm6115/qcm2290`** (linux
  `1afad790b`): `clk_smd_rpm_handoff()` votes INT_MAX into both RPM sets for every clock
  and nothing clears it — the upstream QCM2290 "skip proxy votes" discussion applies to
  khaje (our DT binds `rpmcc-sm6115`). Hardware test: clean boot, sound card and all
  remoteprocs up, hook suspend cycle passes — **but APSS `XO shutdown count` stays 0 and
  vlow Count stays 0**. The proxy votes were not our blocker: the remaining xo holders
  are real consumers — the remoteprocs keep running through suspend, and the femto USB
  PHY keeps its `ref` (bi_tcxo) prepared because the EUD holds it powered (patch 0029).
  The patch stays (upstream-aligned, harmless, the right bring-up direction); the true
  XO-off path on this board requires the femto-PHY power-cycle to survive resume (hangs
  today) and remoteprocs to power down — the same list as before.
- **Traps from the day**: `make modules_install` streamed its tar onto a rebooting tablet
  once — the module tree was incomplete at udev coldplug, so remoteprocs, sound and the
  rest never autoloaded, and everything else (ASoC "no card", missing remoteprocs) looked
  like a regression from the clock patch. Run `mods.sh` only when the tablet is fully up,
  never right after `kup.sh` (it reboots). `modprobe` "not found" with all files present
  = stale `modules.dep` — `depmod -a` on the tablet. kmod 34.2 on pmOS.

**Both cmdline flags dropped (same day, after 0045).** Rebuilt without
`clk_ignore_unused pd_ignore_unused`: boot healthy — sound card registers (no
`can't create pcm: -110`), remoteprocs up, two full hook suspend cycles clean,
`hangcheck` count 0, no GPU lockups, gadget rebinds. The Nov-13 no-flags
failures (audio -110 at boot, GPU lockup after resume) are cured by the fixes
since — 0045 (no more INT_MAX proxy votes on the smd-rpm bus clocks) is the
prime suspect. `mkboot.sh` default CMDLINE is flagless now; the flags can still
be added back ad hoc for debugging. Note the full pmOS boot (OpenRC to sshd)
takes ~2 min — ssh loops that give up earlier look like dead boots.



## Bluetooth audio (2026-10-31)

Earphones paired and connected but had no sink. Three separate causes:

- Kernel lacked `BT_RFCOMM`, `BT_BNEP`, `BT_LE`, `INPUT_UINPUT`. BlueZ logged `RFCOMM server failed` and `AVRCP: failed to create uinput`. All on now.
- Greeter's PulseAudio (uid 105) outlives the greeter, its runtime dir gone, nothing can reach it, and it holds the A2DP endpoints. `/var/lib/greetd/.config/pulse/default.pa` includes the stock
  file and unloads `module-bluetooth-policy` and `module-bluetooth-discover`. Belongs in the device package. Check with `logread | grep -c "Endpoint registered"`: 0 at the greeter.
- The session's PulseAudio only registers endpoints if it starts with Bluetooth available: after `rfkill block` it stayed silent until `pulseaudio -k`. `rfkill block` also survives reboots here (`/var/lib/rfkill`).


## Calls and SMS (2026-10-31)

`calls` and `chatty` are in `build/pmos/world`. Calls saw the modem through ModemManager, Chatty started. USSD works with `mmcli --3gpp-ussd-initiate`, the operator's reply lands in the `network notification` field while the call itself ends in `Aborted: USSD terminated by network`. The Phosh dialer shows nothing for such a reply.

Voice call audio has no path yet: no q6voice driver in `sound/soc/qcom/qdsp6` and no `VoiceCall` verb in our UCM. SMS is untested.

## Desktop (2026-10-31)

Phosh runs: `postmarketos-ui-phosh` on the existing rootfs, GPU-rendered, greeter on the panel. Packages were fetched on the host and installed
from a local repo, which needs a `noarch -> aarch64` link; the USB proxy is too slow for it. Suspend doesn't exist yet.

- Added by hand: `user` (uid 10000), `/etc/NetworkManager/conf.d/50-aupad-usb0.conf` (NetworkManager must not touch
  usb0), `/etc/elogind/sleep.conf.d/50-aupad-nosuspend.conf` (suspend is untested).
- **Rotation needs three settings together.** phoc ignores the panel's `rotation=<180>`, so `/etc/phosh/phoc.ini` has `[output:DSI-1] rotate = 180`.
  Touch needs `/etc/udev/rules.d/60-aupad-touch.rules`, `LIBINPUT_CALIBRATION_MATRIX=-1 0 1 0 -1 1`. Match `DRIVERS=="edt_ft5x06"`, not the name: it ends in a byte read from the controller, usually `(e4)`, once `(ef)`, and a name match then silently loses the calibration. The sensor needs the mount matrix above.
  Weston behaves differently and would need the touch rule removed. All three belong in the device package.
- Boot and session fixes: `swapfile` and `/etc/init.d/swap` collide with zram's
  virtual `swap` (services wait about 50 s, rc-update prints `swap is the name of a real and virtual service`); `kill-plymouth` removed; Evolution
  alarm, Smartcard, PrintNotifications, Wwan and UsbProtection autostarts hidden; tty1 getty off.
- Run `rc-update -u` after adding services: a stale cache silently skipped dbus and bluetooth.
- Cmdline drops `console=tty0 fbcon=...`: the panel shows no text, kernel log and emergency access are UART only.
- nftables runs now that the kernel has it. `apk-polkit-server` doesn't start: its binary is missing. `localsearch-3` (pulled in by Files) needs its autostart hidden too.
- On networks that block the package mirrors, run `tools/usbproxy.py` on the host and `apk` with `http_proxy` and `https_proxy` set to `http://172.16.42.2:8888`. It only serves `apk`, and there is no NAT over USB.

## Audio (2026-10-31)

Speakers work from apps through PulseAudio, and volume keys and slider work. The internal mic delivers signal, about -72 dBFS in a quiet room, but nobody has judged a recording by ear yet.

- **Firmware:** the ADSP runs AudioReach (GPR), not sm6115's APR. No userspace helper is needed: Android's `audioadsprpcd` starts a static `audiopd`, but here macros, SoundWire and playback all work without it.
- **Topology:** mainline needs `qcom/sm6225/CHUWI-AuPad-tplg.bin`. Build `build/pmos/audio/CHUWI-AuPad.m4` inside https://github.com/linux-msm/audioreach-topology: `m4 -I . CHUWI-AuPad.m4 > aupad.conf`, then `alsatplg -c aupad.conf -o CHUWI-AuPad-tplg.bin`. It warns about undefined `RX_CODEC_DMA_RX_0 Playback` and `TX_CODEC_DMA_TX_3 Capture` routes, and the result still loads. Install it under `/lib/firmware/`.
- **UCM:** copy `build/pmos/audio/ucm2/` to `/usr/share/alsa/ucm2/`, and `audio-gain.start` to `/etc/local.d/`, then enable `local`. Everything here is installed by hand and belongs in the device package.
- **Hardware:** RX, TX and VA macros (stock calls it Bolero 2.1, the VA macro reports v2.2), WCD9370 on SoundWire (`swr0` RX; `swr1` TX, under the VA macro), two AW87xxx amps on the HPH outputs (GPIO 100 and 98, `aw8738` driver, 2 pulses). Each amp drives two speakers: left is the top pair, right the bottom pair in portrait. So landscape gives real stereo, and a swap by orientation would only help there.
- **Votes:** only `LPASS_HW_DCODEC_VOTE` works. With the MACRO vote the firmware answers error 1 and nothing probes.
- **`RX HPH Mode` must be `CLS_H_LOHIFI`,** with `RX_HPH PWR Mode` `LOHIFI`. At its default the amps only buzz at the period rate, 50 Hz with 20 ms periods.
- **HPH data stays on lane 1.** Lane 0 gives `SWR Port collision detected`.
- **Left channel:** `wcd937x-sdw.c` wrote the binding's 12 `tx-channel-mapping` values into an 11-entry table, past its end, and HPH_L's `ch_mask` became 8. The loops are bounded now. Worth sending upstream.
- **Internal mic:** stock's ADC1 path is master TX port 2, so `qcom,tx-port-mapping = <2 2 3 3>` and `SWR_MIC4`. The QCM6490 mapping gives digital silence. It goes through DEC0: with stock's DEC2 the DMA never delivers a sample. Only the first capture channel carries signal, so mono mixdown may lose about 6 dB.
- **Volume is software only,** so the UCM profile names no mixer element. The driver's HPHL/HPHR dB scale is wrong and PulseAudio pushes the real gain to almost nothing, and the digital gain reaches +40 dB. Hardware stays fixed 14 dB under stock. Never test with a full-scale tone: at stock gain it's painfully loud.
- **Jack:** the development tablet's socket ribbon is disconnected, and false plug events made PulseAudio switch the speakers off. So the installed profile has only Speakers and Mic1. `build/pmos/audio/HiFi-with-jack.conf` adds Headphones and the headset mic, but it can't work until that's reconnected, and its jack switching is untested.

## Boot hang, open (2026-10-31)

**The worst open bug.** On some boots, 2 in about 30 when first measured, the whole SoC freezes 9-10 s in, during module loading. A disk kernel with no
host attached is then stuck in ramdump, so keep the tablet connected.

- No oops, no RCU stall, no watchdog message. About 6 s later a reset into ramdump. Reset status is 3 in both dumps.
- One capture ends at `Bluetooth: SCO socket layer initialized`, right before the DSP starts. Another ends at
  `Booting fw image qcom/sm6225/aupad/cdsp.mdt`. So both are around the concurrent PAS starts in TrustZone.
- Same signature as the `/pmu` hang in Stability gotchas, whose cause was never found.
- The earlier ramdumps "on reboot" are probably this hang on the next boot: the first was seen without UART, so that's an inference.
- Ruled out by reading only: `qcom_rng`, which has its own clock and is used the same way on stock.
- Not reproduced by replacing modules and rebooting (4 of 4 fine), or by plain reboots (4 of 4 fine, later 2 of 2).
- Capturing one: `tools/uartd.py` keeps the UART recorded and runs `build/rdcap.sh` on any ramdump. It reads Sahara memory-debug mode (05c6:900e) over raw USB. A USB port reset gives a fresh HELLO, the zero-length packet after each
  read of a 512-byte multiple must be consumed, and the reset reply must be read or the device doesn't go on. The kernel is at 0x80600000 via
  U-Boot. Search RAM for the log text rather than trusting `__log_buf` from `System.map`.
- Next: measure the rate over about 20 reboots, repeat with DSPs started one at a time, pull CPU contexts from the dumps.

## Standalone boot (2026-10-30)

ABL -> recovery_b (stub + U-Boot) -> 1 s autoboot -> `/boot/boot.img` on `pmos` (`scsi 0:b`) -> `bootm` -> initramfs
-> switch_root. The file is the same Android image `fastboot boot` takes. If loading fails, U-Boot starts fastboot.

- `build/kup.sh [image]`: install a kernel on running pmOS and reboot; the old one stays as `/boot/boot.old`.
- `build/ub.sh` still works: `tools/ubstop.py` sends spaces during reset, catches the `=>` prompt and runs fastboot.
- Update U-Boot: patch, build, `mkstub.sh`, chain from RAM first with `fastboot boot build/boot-ub2.img`, and only
  then `build/fl.sh`. With misc set, a broken recovery_b loops, and `adb reboot edl` needs Android.
- Measured: HS-G3 x2, 57 MB read in 75 ms, Linux re-initialises UFS after U-Boot without trouble.
- U-Boot's ext4 doesn't replay the journal: `sync` after changing `/boot` (kup.sh does).

Open risks:
- Without a host a watchdog reset ends in ramdump (05c6:900e), which only `tools/sahara_reset.py` leaves. Stock
  Android has the same ramdump mode; finding the switch that disables it is still to do.
- A kernel on disk that hangs reboots into itself until the UART stops autoboot: no boot counter yet.
- Charging works on bootloader settings, with no driver; behaviour at low battery is untested (see Power).

## Power (2026-10-30)

- `/sys/class/power_supply/cw2015-battery`: capacity, voltage, status, current. No battery profile in the DT, so the driver
  keeps what's stored in the gauge. Design capacity is 7000 mAh from public specs, not measured. Stock's 3812 mAh comes
  from a generic "Alium 3600mAh" QG profile, so ignore it.
- `qcom_smb5` (`charger@1000`, `reg` also has QG at 0x4800) is read only and gives `pm7250b-charger`. Online is
  0x110b & 0x11. Status is 0x1006 low 3 bits, as in stock `smblib_get_prop_batt_status`. SMB2's `qcom_smbx` doesn't fit:
  other offsets, 0x1007 bit 1 is OV, and it writes init values at probe.
- Battery current is QG 0xc6 read with 0x42 bit 0 held, and 305.176 uA per bit on QG subtype 4 (from stock
  `qg_get_battery_current`). The QG runs on bootloader settings. Scale is unchecked against a meter. `qcom_smb5` gives it to
  `cw2015` over IIO, positive when charging. While the charger is charging, below -50 mA it reports Discharging: 500 mA
  input loses to load (8 spinning CPUs: about -400 mA). `cw2015` skips its 30 min "SoC stuck" gauge reset when it has this channel.
- Measured on USB at 98%: +145 mA idle, Charging; about -400 mA under load, Discharging; back within 5 s. Status
  follows within one 8 s gauge poll. Phosh icons for charging, full and unplugged confirmed by eye.
- PM7250B ADC in `/sys/bus/iio/devices` (`pmic@2`): `vbat_sns`, `usb_in_v_div_16`, `usb_in_i_uv`, temperatures.
- Charger registers, read through `/sys/kernel/debug/regmap/0-02/registers` (reading it walks 64K SPMI registers):
  0x1042 charging enabled = 1, 0x1006 low 3 bits = 3. **It charges:** stock `qpnp-smb5-main.ko` has INHIBIT 0, TRICKLE
  1, PRE 2, FULLON 3, TAPER 4, TERMINATE 5, PAUSE 6, DISABLE 7, and maps 3 to fast charge. Float/current scaling of
  0x1070 = 0x4b and 0x1061 = 0x28 (about 4.35 V, 2 A) is unverified. Not tested from a low battery.
- USB input sits near 4.60 V, and with no driver nothing raises the input limit from the 500 mA Android reported.
  Heavy load can probably out-draw it.
- Other I2C1 devices in the stock DT: pm8008 @8, smb1355 @c (absent at runtime on Android: no driver bound), LED.

## Storage layout

`pmos` is a partition added on LUN 0 by shrinking `userdata`: `tools/gptsplit.py` writes new GPT images and touches
nothing else. Here `userdata` became sda10 at 32 GiB and `pmos` sda11 at 73 GiB, Linux filesystem type. This wipes `/data`.

## Android-free loop (2026-10-30)

Chain: ABL -> recovery_b = `stub` (arms 120 s APSS watchdog) + U-Boot -> `fastboot boot` -> mainline.

- `build/ub.sh <img> [secs]`: the normal test loop. RAM boot, about 8 s, no flash writes. Gets to U-Boot from any
  state (mainline, Android, ramdump) by itself. A hung kernel: ramdump -> sahara_reset -> U-Boot in 19 s.
- `build/fl.sh <img>`: from running mainline, push over USB; `flash` writes recovery_b, verifies, `rb recovery`.
  Use it to update U-Boot: `PAYLOAD=build/uboot/u-boot-nodtb.bin EXTRA=-DSTUB_WDT=120 stub/mkstub.sh build/boot-ub.img`.
- **misc holds `boot-recovery` in its first 32 bytes**, so every plain reboot goes to U-Boot, and **Android does
  not boot until it is cleared**. `ub.sh build/boot-bcbclr.img` puts back the original (`qmmi`, from
  `build/tests/misc.head`; tested). Don't zero it. To set it again: write `build/bcb.bin` from Android.
- ABL ignores volume keys for boot selection: VOL+ and VOL- give `KeyPress:1/2` but `Recovery:0`, `Fastboot=0`.
  `rb recovery` from mainline works (PON spare, one-shot) through `pm6125.dtsi`.
- Watchdog: the reset comes about 9.6 s after the timeout, then ramdump. U-Boot autostarts it (30 s) and
  pets it, the kernel takes over with built-in `QCOM_WDT`, so an unpetted hang resets itself.
- Screen: U-Boot prints to vidconsole, the kernel to fbcon with `console=tty0 fbcon=font:TER16x32` (use
  `scripts/config -k` for that option: without it, the name is uppercased and silently ignored).
- U-Boot: `build/uboot`, configured with qcom_defconfig + qcom-phone.config, then PANIC_HANG off,
  TOOLS_MKEFICAPSULE off, `board/qualcomm/aupad.env` (from the U-Boot patches). Uses ABL's DT via x0. `O=` must be
  absolute. fastboot address 0x805ff000 is deliberate: kernel lands 2 MB aligned, so bootm doesn't move it over
  the DTB in the same buffer ("image is not a fdt").

## Boot / test loop (ABL gotchas)

- ABL refuses `fastboot boot` and `fastboot flash`. Test images go to **recovery_b** (100 MB), written from
  rooted Android or EDL. Normal testing is `build/ub.sh` now. boot_b is never touched.
- **Kernel must be an uncompressed Image.** With a gzipped kernel in a header-v2 image, ABL decompresses
  it but never reaches its entry point; the watchdog then bites about 9.5 s later and you land in XBL
  ramdump (05c6:900e).
- DT must have `splash_region@5c000000` (label `cont_splash_region`). Otherwise ABL powers the display
  down at ExitBootServices. With it, the splash framebuffer stays scanned out, so simplefb is usable.
- ABL loads a raw kernel at 0x40000000 and puts the DTB at about 0x4545c000 and the initrd just below
  0x45700000. Entry is at EL1 with the MMU off; the watchdog is off.
- `stub/`: a bare-metal pre-kernel stub (`stub/mkstub.sh` → `build/boot-stub.img`).
  - Enables the QUP clocks and initialises the UART like earlycon, plus the serial clock divider.
  - Prints the handoff state and keeps a RAM log and stage word at 0x5c000000.
  - Then moves the kernel to 0x40200000 and jumps to it.
  - `STUB_PROBE 1` turns it into a PSCI reset-timing probe.

## Stability gotchas

- `gpio-reserved-ranges = <0 4>, <14 4>` on TLMM is mandatory, or boot hangs right after the GIC.
- The `/pmu` node is deleted in sm6225.dtsi. With the PMU driver bound, about 1 s without a CPU reaching
  idle hangs the whole SoC (no oops, no RCU stall), then warm reset to ramdump. Happens with nosmp and with
  every /soc node disabled. Root cause unknown; stock declares the same PPI 6 plus `qcom,irq-is-percpu`.
  Ruled out: RAM (memtest), the stub, kpti/ssbd/KASLR, SMMU, USB, simplefb, tsens, icc votes and QoS, and
  the XO rate (re-tested 2026-10-30 with XO fixed: still hangs within a second of the 3 s spin).
- `&xo_board` (19.2 MHz) and `&sleep_clk` (32764 Hz) must be set in the board DT. sm6115.dtsi leaves them
  empty, every XO-derived rate then reads 0, and cpufreq-hw fails with "Failed to add OPPs".
- PHY rails: L4 880 mV, L12 1.704 V, L15 3.05 V (read from running Android). Without these minimums
  RPM brings them up at the bottom of the range.
- No USB3 PHY described yet, so `&usb` needs `qcom,select-utmi-as-pipe-clk`.
- TLMM: downstream khaje matches sm6115 (same tiles). Pin 113 is `UFS_RESET`, as in mainline and on live
  Android; the public downstream tree's pinctrl-khaje.c numbers it 120, but it is the same register, 0x578000.
- `CONFIG_PHY_QCOM_USB_SNPS_FEMTO_V2` is required for the HS PHY.
- CPU thermal: sm6115.dtsi has no CPU cooling maps. sm6225.dtsi adds a 95 C passive trip on all CPU zones.
  Without it, full load reached 90.7 C in 3.5 min at full speed. Stock's own passive trip is 110 C.

## Clocks (GCC)

`drivers/clk/qcom/gcc-sm6225.c` is generated: `tools/gcc_port.py <downstream gcc-khaje.c> <sm6115 driver> <out>`.
Don't hand-edit its data, fix the script. It strips downstream voltage voting, turns parent names into `parent_data`/
`parent_hws`, keeps every register value, and takes GDSCs from gcc-sm6115.c (addresses match the stock DT). RCG ops
are mainline's for that name, else `clk_rcg2_shared_ops` where downstream had `enable_safe_config`.

- Source: GPL-2.0 downstream kernel, https://github.com/mi-sdm680/android_kernel_xiaomi_sm6225, `drivers/clk/qcom/`.
- khaje PLLs are Lucid, gpll9 Zonda; the sm6115 driver reads them wrongly.
- Uses the sm6115 binding with IDs added (167-175, reset 12) so `sm6115.dtsi` keeps working. A real binding is
  needed for upstreaming. `gcc_camera_xo`, `disp_xo`, `gpu_cfg_ahb`, `cpuss_gnoc` are always on, not exposed.
- Verified 2026-10-30 against the clock summary on Android: all 16 PLL rates match (gpll3/7/8 differ by alpha rounding,
  under 100 Hz); among clocks enabled on Android only USB3 differs (133 vs 66 MHz, 1000 vs 0 Hz pipe), because
  USB runs HS here. UFS read is the same on old and new driver: 541 vs 542 MB/s (2 GB buffered `dd`, second run on).
- gpll8-11 are now configured at probe, as downstream does. Not exercised by any consumer yet.

### dispcc and gpucc

`dispcc-sm6225.c` and `gpucc-sm6225.c` are generated by `tools/cc_port.py <dispcc|gpucc> <downstream.c> <sm6115 driver>
<out>`, same rules as GCC. Binding IDs added: DISP_CC_MDSS_RSCC_AHB_CLK 22,
RSCC_VSYNC 23, GPU_CC_PLL0_OUT_MAIN 17. `SM_DISPCC_6115`/`SM_GPUCC_6115` are off.
Verified: gpu_cc_pll0 640 MHz, pll1 690 MHz, GPU SMMU probes (was -110).

## Display (2026-10-30)

Stock cmdline names the panel: `qcom,mdss_dsi_ft8201p_cw_10_51_video`. 1200x1920, 4 lanes, RGB888, video mode, non-burst
sync events; 170.98 MHz pixel clock matches Android. `drivers/gpu/drm/panel/panel-focaltech-ft8201p.c`
holds the 176 init commands from the stock DT . All are generic long writes,
LP mode, and they include a sleep in/out, which is stock behaviour. It is a module, as is `msm`; udev loads both.

- HW: MDSS 6.10 (`0x600a0000`), DSI 6G v2.4.1 (`0x20040001`), DSI PHY v4.1. Block layout is identical to mainline's
  sm6115 DPU catalog, so `qcom,sm6115-dpu` stays. PHY uses `qcom,sm6375-dsi-phy-7nm`. UBWC 1.0 like sm6115:
  `qcom,sm6225` added to `ubwc_config.c`, which matches on the root compatible.
- MDP OPP table replaced: sm6115's rates don't exist on khaje's RCG, corners are from dispcc-khaje.c.
- **The stock GDSC node name lies:** `qcom,gdsc@5f03000` has `reg = <0x5f01004>`. `gdscr = 0x1004`, BCR 0x1000, as on
  sm6375. Always read `reg`, not the unit address. With 0x3000: `mdss_gdsc status stuck at 'off'`.
- Pins: reset 82 (active low, stays high), bias ENP 102, ENN 85, TE 81 unused.
  VDDIO L9 1.8 V, DSI L18 1.2 V, PHY L4 0.9 V. Refgen is not described: ABL's state is relied on.
- LP6280S (i2c1 0x3e, `lp6280s.ko`) has no driver: ABL's voltages are kept, its input is never cut.
- Backlight: PM6125 PWM channel, subtype 0x0b, at SID 1 0xb300, `qcom,pm6125-pwm` added to leds-qcom-lpg. Period must
  be ABL's 106667 ns: with the stock 100 us the driver rounds to 79.8 us and keeps the on-time, so duty comes out wrong.
- Touch: mainline `edt-ft5x06`, `focaltech,ft8201`, i2c2 0x38, IRQ GPIO 80, firmware in the chip's flash. ABL leaves
  reset GPIO 86 low, so it must go to the touch driver or the probe fails. Chip ID 0xe4 shows as "generic ft5x06".
  Raw coordinates are 180 degrees from the framebuffer, on purpose: the panel has `rotation = <180>`, compositors
  rotate the output and expect touch in that rotated frame, as stock does. No `touchscreen-inverted-*`: with them Weston
  was mirrored on both axes. Only a raw fbdev test pattern looks inverted.
  Known quirk: with several far-apart fingers one finger flips between two tracking IDs every 16-20 ms, which gives
  fake up/down pairs. Reported on stock Android too. The driver passes through what the firmware sends; a filter
  would have to go in the driver. `tools/evdec.py` summarises a raw `/dev/input/event0` capture.
- Check it runs without eyes: `peek 0x5e6b8ac` (INTF_1 frame count) grows by 60 per second.
- `tools/peek/peek.c` reads single registers, `tools/ubcmd.py` runs U-Boot commands. **Don't read
  `/sys/kernel/debug/regmap/*5f00000*/registers`:** the walk crashed the SoC into ramdump.
- **MDSS needs `DISP_CC_MDSS_AHB_CLK`,** which mainline's sm6115 node lacks; sm6225.dtsi adds it (sm6115 may need the same).
  Without it the first enable works only because ABL left the clock on. After any power cycle `HW_VERSION` reads 0
  or a stale value, `msm_mdss_enable()` silently skips UBWC setup, `UBWC_STATIC` (0x5e00144) stays at its reset 0xe
  instead of 0x11f, and every UBWC buffer scanned directly on a plane comes out as shuffled tiles. Composited windows
  look fine, because the GPU reads them. Weston's first window hit this. Not HW_CTRL, not timing, not fast clear.
- Noise to look at: two `DSI PLL(0) lock failed` during probe (later enable locks), `Lucid PLL latch failed` once,
  zero divisor WARNs. MDP only ran at 200 MHz so far, so disp_cc_pll0 retuning under load is untested.

## GPU (2026-10-30)

Adreno 610 v2, stock chipid 0x6010001, runs as `qcom,adreno-610.0` (0x6010000), GMU wrapper. Firmware: `a630_sqe.fw` and
`a610_zap.*` come from your device's `/vendor/firmware` and go in `/lib/firmware/qcom/` (`mkrootfs.sh` takes them from `firmware/`). Userspace on the tablet: Mesa 26.1.6
(`mesa-dri-gallium`, `mesa-vulkan-freedreno`, `vulkan-loader`), `kmscube`, Weston 14 with `seatd`.

- **Mainline bug, fixed here, worth sending upstream:** `zonda_pll_adjust_l_val()` wrote `rate` instead of `quotient`
  into L. Any Zonda rate with alpha >= 0x8000 (600 MHz here) got a garbage L, `gpu_cc_pll0 failed to enable!`, then
  ramdump. Also added `clk_zonda_pll_recalc_rate()`: alpha with its MSB set is negative, as downstream does.
- OPP table: speed bin 0 of the stock DT, 320-1260 MHz, with CX corners and `opp-peak-kBps` from `qcom,bus-table-ddr`.
  The DDR vote nearly doubled the score at 320 MHz: 2.72 to 5.15 fps. Fuse is elsewhere on khaje, nvmem cell deleted.
- **MX is not voted.** Stock votes vdd_mx by PLL VCO rate (nominal above 2400 MHz VCO, so for 1260 MHz). Mainline's
  GPU node has CX only. No corruption showed up, but that is a gap, not proof it's unnecessary.
- `tools/gpustress` compares each frame's hash against a reference, `build/tests/gpusweep.sh` pins each OPP. Result: 7
  rates clean, 3-minute soak at 1260 MHz, 2174 frames checked, 0 bad, 44 C peak, 12.1 fps. Mostly a CPU readback test
  above 785 MHz, not a pure GPU score. `msm` wait-boost raises the rate during fence waits, so userspace pinning below
  about 1 GHz doesn't hold: cur_freq shows more than the pin. Not a bug.
- `tools/usbproxy.py` gives the tablet package access, USB link only, no host network changes. Use
  `https_proxy=http://172.16.42.2:8888` with `apk`. About 300 KB/s.
- One ramdump happened on a plain `reboot` while testing MDSS (2026-10-30), cause not found, UART not captured.
- A file written just before a crash can come back as zeros, `sync` first. `gpusweep` did exactly that.
- Weston test: `seatd`, then `weston --backend=drm --renderer=gl --drm-device=card1 --shell=desktop`.
- Noise: `devfreq: Couldn't update frequency transition information`.

## UFS

- PHY table comes from stock `phy-qcom-ufs-qmp-v4-khaje.ko` in vendor_boot (`phy_cal_table_rate_A_no_g4`, used
  because `limit-phy-submode` is 0). It is sm8150's serdes unchanged; TX, RX and PCS differ slightly. Lane 2 =
  lane 1. To re-extract: the tables are {u32 reg, u32 val} pairs in the module's .data.
- Rails (stock, not the j606f values): vcc L24 2.96 V, vccq2 L11 1.8 V, vdda-phy L4, vdda-pll L18 1.2 V.
- `limit-hs-gear = <3>` caps the host and `phy_gear`.
- Test safety: `blockdev --setro` every disk first. A partition honours its whole disk's ro flag, so dd to a
  partition fails while the parent is ro. Check dd's byte count: a failed write still matches its own hash.

## Tools

- `build/ub.sh <img> [secs]`: the normal loop, see Android-free loop.
- `test=<name>` on the cmdline runs `/bin/t-<name>` from the initramfs (`build/tests/`).
- The UART link queues. A flood of characters reaches U-Boot late and aborts fastboot with `Operation aborted.`; `tools/ubstop.py` is paced for this. Send commands one character at a time.
- A test must never end parked: nothing but a person on the power button gets a parked CPU back.

## Rig

- Serial console on the debug UART (1.8 V, gpio12/13). The scripts look for a USB adapter named `nanobridge`: change
  the glob in `tools/*.py` and `build/ub.sh` for yours.
- Unbrick: EDL with a firehose loader, bkerler's `edl` works. **Keep your own full backup first.** Never switch to
  slot A: the slot switch on this device also swaps partition type GUIDs.

## Debugging over USB: Qualcomm EUD (Embedded USB Debug)

EUD is a debug block inside Snapdragon SoCs that sits between the USB connector and the USB PHY. Once enabled it shows up on the host as a 7-port USB hub, `05c6:9500`, with its functions behind it: control `05c6:9501`, SWD `05c6:9504`, COM (UART) `05c6:9505`. That gives JTAG/SWD debugging and a serial console over the ordinary USB-C cable, with no JTAG probe, no UART wiring and the case closed, and it keeps working when the kernel's USB stack or the whole of Linux is dead. Whether it can be enabled depends on the device's fuses and debug policy. Here the stub enables it with secure monitor calls (SCM) before the kernel starts, `-DSTUB_EUD`. Background: [Linaro, "Hidden JTAG in a Qualcomm Snapdragon USB port"](https://www.linaro.org/blog/hidden-jtag-qualcomm-snapdragon-usb/).

Debug image, EUD version 7 on SM6225. `nokaslr` keeps symbols valid; the defconfig ships `DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT` and `GDB_SCRIPTS` for source lines and the `lx-*` commands (`make scripts_gdb` writes `vmlinux-gdb.py` to `build/out/`, not `build/out/scripts/gdb/`):

```
CMDLINE="earlycon=qcom_eud,0x1610000 console=ttyMSM0,115200n8 keep_bootcon ignore_loglevel clk_ignore_unused pd_ignore_unused rdinit=/init panic=10 root=pmos nokaslr" \
EXTRA="-DSTUB_WDT=120 -DSTUB_EUD=20" stub/mkstub.sh build/boot-eud.img
```

### Kernel console without a UART: EUD COM earlycon

`drivers/tty/serial/qcom_eud_earlycon.c`, `CONFIG_SERIAL_QCOM_EUD_EARLYCON`. `earlycon=qcom_eud,0x1610000 keep_bootcon` on the command line, `-DSTUB_EUD=20` in the stub, Host: `venv/bin/python tools/eudlog.py`, leave it running, it follows reboots and appends to `logs/eud/`. No gadget or Linux USB involved.
- Starts at the first kernel line, `[0.000000] Linux version`, replayed from the log buffer once `earlycon` is parsed. Nothing from the stub or a crash before `parse_early_param`. The stub holds up to 20 s and releases 1.5 s after it sees the host's `COM_EN`, so about 3 s after the logger attaches.
- Tested: 10000 lines exact and in order, last line of a panic arrives, runs beside OpenOCD SWD and GDB, no host means no output and a normal boot. `earlycon` takes one device, so the UART starts at `ttyMSM0`, without its own early output. Speed is capped by the UART while `ttyMSM0` is a console, about 150 lines/s, and a burst stays queued: count after it drains.
- `0x1610070` mirrors the low byte of the host's CTLOUT, bytes repeated across the word; `COM_EN` is bit 5. The console reads it and drops output with no host. Kernel header calls `0x74` CTL_OUT_1, that's the next byte.
- **The block has to be mapped non-posted.** With `ioremap` or `earlycon`'s posted mapping about 1 packet in 1000 is lost or damaged, and a read back after each byte or waiting for ready to drop only reduced it: 197 lost and 135 damaged of 200000. `ioremap_np`: none of 200000, the driver remaps its fixmap page. Writing `LEN` after the bytes sends nothing. RX still unsolved.

### Two-way console without a UART: ttyEUD0 and U-Boot on EUD COM

Kernel `/dev/ttyEUD0` (`CONFIG_SERIAL_QCOM_EUD`, `console=ttyEUD0`, takes over from the `qcom_eud` earlycon with no gap) and U-Boot (`CONFIG_SERIAL_QCOM_EUD`, `SERIAL_PROBE_ALL`, env console on `serial@1610000`). `build/pmos-install.sh` adds a root getty on ttyEUD0. Host: `tools/eudlog.py`, which records output and offers input as a pty at `/tmp/aupad-eud`.

- RX protocol, measured on SM6225: a host packet is one OUT transfer of exactly `[0x90, len <= 14, data]`, pending until `RX_DAT` has been read `len` times. Further transfers fail while one is pending, and one colliding with a read can shorten or drop it, so the host sends one packet at a time and the tablet acks each with an ID 0x91 packet. COM commands (from github.com/quic/eud): `PORT_RESET` 03, `RX_TMOUT` 02 + u32 LE ms; an expired packet leaves RX dead until a reset, and `ff ff` (Qualcomm's own host value) stops RX events. `eudlog.py` sends `PORT_RESET`, `RX_TMOUT` 0xfffe and a hello on connect; a `-DSTUB_EUD` stub waits for that hello.
- Two console modes on the EUD COM, never both on one command line: `earlycon=qcom_eud,0x1610000 keep_bootcon` (the boot console stays for the whole run, no `/dev/ttyEUD0` console) or `earlycon=qcom_eud,0x1610000 console=ttyEUD0` (clean handover, no `keep_bootcon` — with it both writers keep hitting the same FIFO). `build/mkboot.sh` refuses the combination. Both modes verified on hardware: the handover lands at ttyEUD0 registration with no gap and no duplicated lines, and the getty prompt arrives through the same COM.
- Turning EUD off from the host does not work on SM6225: `CTLOUT` bits `SRST_N` (0, also as a reset pulse), `EDL_REQ` (1) and `HOST_EUD_DIS` (16) all read back as written and none does anything — no reset, no mux switch. From the target it is a plain register write: `poke 0x1611014 0` (built from `tools/peek`; the address is outside the serial driver's claimed region, so it survives `IO_STRICT_DEVMEM`). The next warm boot then runs the stub's cold path: it re-enables EUD and waits for eudlog's hello, releasing in ~4 s with the host attached, or after the full `-DSTUB_EUD` timeout with no host and booting anyway (measured 29 s vs 13 s to the first kernel line).
- **The only host-driven hard reset is SRST through the EUD SWD function** (`eud_reset` in OpenOCD's eud driver clears `RCTLR_SRST_N|GPIO_SRST_N` in the bitbang engine; `tools/ocd/srst` does the whole dance: fresh server, pulse, report). Measured on SM6225: SRST from running Linux boots into **EDL** (`05c6:9008` or `05c6:900e`, CPU "divar"); SRST from an EDL/firehose state boots **normally** — that is the reliable way out of EDL; a firehose `power reset` and a power cycle from EDL both come back up in EDL. The EUD hub stays alive in EDL, which is why the CTL/SWD dance still works there. JTAG (0x9503) adds nothing for resets: TRST only resets the TAP.
- **EDL from Linux, the clean way: the `qcom_scm` `edl` parameter** (kernel series 0033/0034). The scm node carries `qcom,dload-mode = <&tcsr_regs 0x13000>` — TCSR `BOOT_MISC_DETECT` at `0x3d3000`, the same register stock's `adb reboot edl` writes through TrustZone (`QCOM_DOWNLOAD_EDL = 0x01`; bits 4-5 are the dump modes of the `download_mode` parameter). `echo 1 > /sys/module/qcom_scm/parameters/edl; reboot -f` comes up as a clean `05c6:9008` within seconds: no DDR dump pending, `printgpt` works right away. The bit survives both the probe-time and the clean-shutdown `NODUMP` write (mask `GENMASK(5, 4)` leaves bit 0 alone), the boot stages consume and clear it, and the next boot is normal — verified end to end: SRST out of that EDL booted Linux with the parameter back at 0. Without the DT register the parameter returns `-ENODEV` (the `BOOT_SET_DLOAD_MODE` SCM fallback would arm a dump mode, not EDL). The register is TZ-only for the debugger: `mdw phys 0x3d3000` aborts (XPU) and a VA read through the running kernel's MMU hit an unrelated mapping (a 0 once, an abort the next time) — the parameter's own error path is the only observable.
- EDL from a dead kernel (no adb, console gone) needs the SRST path above. bkerler's `edl` (master `1cda1a6`) needs `patches/edl/edl-client-1cda1a6-logless-firehose.patch`: this `prog_firehose_ddr` loader replies without log lines, which crashes stock edl's NAK check on `bytes`, and it never answers the configure probe read, which hangs every command unless skipped. So: `edl --loader=<elf> rawxml '<power value="reset"/>' --skipstorageinit` (`reset` itself takes neither `--skipstorageinit` nor `--memory`, docopt pattern; `printgpt`/`r`/`w` do). The signed firehose is not in the repo (Qualcomm binary, no redistribution): `prog_firehose_ddr.elf`, md5 `f51e62a37c65fd3cf87c7b4c157afff5`, works with SM6225/divar. An SRST entry sometimes comes up crash-dump-pending instead: sahara then dumps DDR (2 GB, ~1 min) before anything else and a dump interrupted halfway desyncs it until the next reset.
- The EUD interrupt (SPI 189) never reaches the GIC, so both drivers poll. 20 KB through the shell intact, 1.6 KB/s.
- The HS PHY must not be reset while EUD is on: patched in the kernel and U-Boot femto PHY drivers (optional `reg` for the EUD enable register). U-Boot's dwc3 peripheral disconnects before "fastboot boot" hands over.
- U-Boot on the current DT needed: serial_msm_geni no longer enables an error-pointer clock, the sm6115 clock driver matches `qcom,sm6225-gcc`, a port failing under `SERIAL_PROBE_ALL` only warns, and `MMC_SDHCI_MSM` off (the SD controller faults without an RPM interconnect vote).
- `tools/tab.py` drives boots with verified steps (`state`, `fastboot`, `boot`, `pmos`, `ramboot IMG [--attach N --ocd CMD]`); `tools/ocd/up --core N` checks that a Kryo core really answers. Stray characters while U-Boot is in fastboot abort it, which is why `ubstop.py` is superseded.

### OpenOCD and GDB: kernel and RPM debugging over SWD

- **`tools/ocd/`: OpenOCD and GDB, debugging all 8 Kryo cores and the RPM (Resource Power Manager, a Cortex-M3) over SWD.** Upstream OpenOCD has an `eud` adapter driver. We use master `f13e839c5` plus `tools/ocd/eud-sm6225.patch` in `tools/ext/openocd`, with jimtcl built into `tools/ext/jim-inst`: `PKG_CONFIG_PATH=$PWD/../jim-inst/lib/pkgconfig ./configure --enable-eud --disable-werror && make`. Needs an image built as above.
  - **`tools/ocd/g kernel [gdb args]` and `tools/ocd/g rpm [gdb args]` are the way in.** `tools/ocd/up` starts or recovers the server, resets the EUD hub when its control function is missing, and `g` calls it. Tcl on 6666, `tools/ocd/oc 'cmd' ...` runs commands. GDB: `rpm` on 3333, the Kryo SMP group on 3334, all 8 cores as threads. `tools/ocd/khaje.cfg` is the target; Kryo needs `kryo` (examine all) first, `g` does that.
  - Verified with GDB 2026-11-01, kernel #43 with DWARF and `GDB_SCRIPTS`: source lines, structs, `lx-version`, `lx-ps`, `lx-dmesg`, `$lx_current()` (gave `sync`, right pid, in a breakpoint), hardware breakpoint on a named core and `finish`, write watchpoint on `jiffies_64` (hit `tick_do_update_jiffies64` on 2 cores, values right), stepi, backtraces from EL1 down to `el0t_64_sync`. `monitor sysregs N` reads the EL1 state; `VBAR_EL1` = `vectors`, `SP_EL0` = `init_task` on an idle core, MPIDR and MIDR right per core. 12 of 12 reconnects, RPM RAM read 55 KB/s without halting, a stop about 0.6 s. Killing GDB with a breakpoint armed clears it and resumes. The patch also adds `aarch64 mrs` and an `SP_EL0` register, and drops the per-collapse reset message to debug level (it was 80 lines/s).
  - **Don't leave the RPM halted.** Linux's regulator request times out, `failed to enable regulators, err=-110` on the UFS PHY, UFS is dead until reboot and userspace sticks in D state. One run, halted about 1 min. A halted-RPM boot is disposable: don't run Kryo tests on it.
  - **Deep idle loses Kryo breakpoints silently.** With `cpu-sleep-0-0` on, `sync` ran on 4 cores and none stopped. `g kernel` turns the state off for the session and refuses to start if it can't. Halting works with idle on, but a core can stop in EL3 at `0x0c100010` or `0x1000e0f4`, where kernel addresses don't translate.
  - Every kernel stop halts all 8 cores. A breakpoint on a hot address stalls the system: `finish` from a syscall hit `invoke_syscall` 35 times and UFS logged `hibern8 exit failed -110`, which it recovered from. Avoid common return addresses.
  - `monitor` doesn't follow GDB's `thread`, it stays on cpu0: pass the core number. All GDB breakpoints are forced to hardware (6 on Kryo, 6 on the RPM), kernel text is read-only and a software one aborts.
  - Earlier, from Tcl, on the RPM: halt, 6 hardware breakpoints armed while running (upper halfword too), single step, registers, NVIC, resume. `DWT_PCSR` reads live without halting. Verified on Kryo: examine, halt and read all 8, resume 2. 12 of 12 connects.
  - `tools/ocd/hunt.py [cycles] [--here] [--fire] [--release]`: reboots, arms `0x21EA2`, `0x21B60` and fault vector catch, stops the RPM on a hit, dumps to `logs/hang/<time>/`, leaves the server up. `--fire` is the forced abort. Reboots through `uartd`.
  - Traps: **`reset_config none` stays, SRST left the tablet in EDL.** `reset halt` is not a way to stop a core here: it resets and halts the RPM first, then dies on `cpu0: how to reset?` — leaving the RPM halted is the `-110` trap above, and `targets cpuN; halt` is the real path. Resuming a target needs `targets cpuN; resume`, and a script that stops at an error leaves the core halted, so a failed `resume` means check `DHCSR`. The RPM can be halted with OpenOCD still calling it `unknown`: `poll` or `halt` first. `pkill -f openocd` from a shell whose command line contains that text kills the shell.
  - **Driver fixes in the patch, all found here:** (1) **SWD clock below 7.5 MHz breaks the EUD's bulk endpoint** with `LIBUSB_ERROR_IO`: 469 kHz, the old default, 4 of 4 failed, 938 kHz 3 of 4, 7.5 MHz and up 0 of 28; (2) open functions only behind hub 9500; (3) release the DAP resets with `BITBANG 0x74` at init, needed with `reset_config none`, and take its reply; (4) cycle `SWD_EN` low on connect; (5) 1 ms gap after a write with no read: back to back failed 4 of 4, 0.2 ms passed, write-read pairs need none, 2000 of 2000 at 10600/s; (6) set the USB configuration before claiming (checked, skipped when already set, `BUSY` tolerated) and log a failed `clear_halt` instead of ignoring it; (7) `aarch64 mrs` from EL0 checks both `modeswitch` results, always restores the mode and finishes the DPM (2026-11-12, verified reading `SP_EL0` from a core halted in EL0T: mrs = `get_reg sp`).
