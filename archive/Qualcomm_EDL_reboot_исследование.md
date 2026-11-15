# Qualcomm EDL reboot: как работает `adb reboot edl` и как воспроизвести

**Дата:** 12 ноября 2026 года
**Предмет:** полный путь команды `adb reboot edl` (подтверждён на планшете со стоковым Android), механизм записи причины перезагрузки в Qualcomm-загрузчики и план воспроизведения из нашей Linux (mainline 7.3.1) и U-Boot.
**Основные источники:** AOSP (adb, init, system/core/reboot), downstream-ядра Qualcomm (msm-4.14/4.19/5.4/5.15), LK (`platform/msm_shared/reboot.*`), mainline 7.3.1 (`drivers/firmware/qcom/qcom_scm.c`), реверс PBL (Aleph Security msm8974, Quarkslab msm8994), DT downstream bengal.dtsi, локальное дерево `linux/`.

## 1. Краткий вывод

1. `adb reboot edl` **не пишет ничего в PON spare регистр**. Для EDL у Qualcomm существует отдельный канал: бит «download mode» в регистре TCSR **`BOOT_MISC_DETECT`** (на Bengal/Khaje — `0x3D3000`), который ядро пишет **через SCM-вызов (TrustZone)**, после чего выполняет **тёплый сброс**. На следующем старте XBL/секция dload-check читает этот бит и уходит в загрузчик QDLoader 9008 вместо обычной загрузки.
2. Значения того же регистра: `0x00` = off, **`0x01` = EDL**, `0x10` = full dump, `0x20` = minidump (`enum qcom_download_mode` в downstream `include/linux/qcom_scm.h`). «Байка» про `0x10 = EDL` неверна — `0x10` это full RAM dump.
3. В нашем дереве 7.3.1 механизм почти готов: `qcom_scm.c` умеет RMW-писать в `BOOT_MISC_DETECT` через SCM (`qcom,dload-mode` в DT + параметр `download_mode`), но его маска `GENMASK(5, 4)` покрывает только биты dump-режимов — **бит 0 (EDL) не доступен из существующего параметра**. Для воспроизведения нужно: одно DT-свойство + ~30 строк патча (параметр `edl`), после чего из busybox: `echo 1 > /sys/module/qcom_scm/parameters/edl && reboot -f`.
4. Сток на SM6225 пишет ровно тот же бит через тот же SCM-сервис, поэтому поведение XBL/PBL гарантированно совпадает с проверенным `adb reboot edl`.

## 2. Пользовательская цепочка Android (проверено по коду AOSP)

`adb reboot edl` — не shell-команда, а специальный adb-сервис `reboot:edl`:

- **Host**, `packages/modules/adb/client/commandline.cpp`: `adb reboot <arg>` формирует строку `reboot:<arg>` и отправляет как сервис; произвольные аргументы (`edl`) проходят без фильтрации.
- **adbd**, `daemon/services.cpp` (Android 11+; в Android 10 — `daemon/reboot_service.cpp`, в ≤9 — `SetProperty` прямо из adbd):

  ```cpp
  } else if (android::base::ConsumePrefix(&name, "reboot:")) {
      return reboot_device(std::string(name));
  }
  ...
  std::string cmd = "/system/bin/reboot ";
  cmd += name;                       // adbd (uid shell) не имеет CAP_SYS_BOOT
  return StartSubprocess(cmd, ...);
  ```

- **`/system/bin/reboot`** — отдельный бинарник `system/core/reboot/reboot.c` (не toybox!): ставит свойство `sys.powerctl = "reboot,edl"`.
- **init**, `init/reboot.cpp` → `HandlePowerctlMessage("reboot,edl")` → `init/reboot_utils.cpp`:

  ```cpp
  case ANDROID_RB_RESTART2:
      syscall(__NR_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
              LINUX_REBOOT_CMD_RESTART2, rebootTarget.c_str());   // "edl"
  ```

- **Ядро** (generic), `kernel/reboot.c`: строка копируется из user (до 256 байт) и уходит в `kernel_restart("edl")` → `machine_restart()` → цепочка restart-обработчиков, где её встречает Qualcomm-код.

Строка `"edl"` проезжает через все звуки дословно. Важно для нас: **busybox `reboot` аргумент не передаёт** (applet `halt.c` понимает только `-d/-n/-f/-i`, `-f` вызывает `reboot(RB_AUTOBOOT)` без строки; toybox тоже) — значит строковый путь RESTART2 из нашего userspace недоступен, нужен свой интерфейс (см. §5).

## 3. Ядро downstream: что сток делает со строкой "edl"

### 3.1 SM6115/SM6225-поколение (msm-5.4/5.15)

`drivers/power/reset/qcom-dload-mode.c` + `drivers/power/reset/msm-poweroff.c` (репрезентативные исходники: [CodeLinaro msm-5.4](https://git.codelinaro.org/clo/la/kernel/msm-5.4/-/blob/LA.UM.10.9.1.r1/drivers/power/reset/msm-poweroff.c), [ядро Xiaomi SM6115](https://github.com/greenforce-project/kernel_xiaomi_citrus_sm6115)):

```c
#define QCOM_DOWNLOAD_EDL  0x01   /* enum qcom_download_mode: NODUMP=0, EDL=1, FULLDUMP=0x10, MINIDUMP=0x20 */

} else if (!strncmp(cmd, "edl", 3)) {
        enable_emergency_dload_mode();
...
static void enable_emergency_dload_mode(void)
{
        ...
        qcom_scm_set_download_mode(SCM_EDLOAD_MODE /* = QCOM_DOWNLOAD_EDL */,
                                   tcsr_boot_misc_detect ?: 0);
}
```

`qcom_scm.c` downstream: если в DT задан `tcsr-boot-misc-detect`, делает **SCM IO write** (`SCM_SVC_IO=5`, cmd=2) значения `0x01` по этому адресу, иначе — SCM-вызов `SCM_SVC_BOOT=1`, cmd=0x10 (`BOOT_SET_DLOAD_MODE`). Адрес для Bengal из DT ([bengal.dtsi](https://github.com/greenforce-project/kernel_xiaomi_citrus_sm6115/blob/qti-perf/arch/arm64/boot/dts/vendor/qcom/bengal.dtsi)):

```dts
restart@440b000 {
    compatible = "qcom,pshold";
    reg = <0x440b000 0x4>, <0x03d3000 0x4>;
    reg-names = "pshold-base", "tcsr-boot-misc-detect";
};
```

Затем — **тёплый сброс** (`PON_POWER_OFF_WARM_RESET` через PS_HOLD, не watchdog, не power off).

### 3.2 Потребитель куки: XBL/загрузчики

- XBL (`boot_dload_check`) читает `HWIO_TCSR_TCSR_BOOT_MISC_DETECT`, маскирует биты DLOAD/MINIDUMP и при установленном бите уходит в downloader (9008), после чего сбрасывает биты. Регистр **переживает reset** (TCSR retained), поэтому куки, записанная до тёплого сброса, видна на следующем старте. Для семейства Bengal куки хранится в `BOOT_MISC_DETECT`, а не в IMEM.
- Историческая справка: на msm8974 PBL сам проверял LSB регистра `0x193D100` ([Aleph Security](https://alephsecurity.com/2018/01/22/qualcomm-edl-1/)); на msm8994 PBL проверял тройку magic в IMEM `0x322A4F99 / 0xC67E4350 / 0x77777777` ([Quarkslab](https://blog.quarkslab.com/analysis-of-qualcomm-secure-boot-chains.html)). В downstream-ядре эта тройка (`qcom,msm-imem-emergency_download_mode`) остаётся, но на современных XBL-поколениях она не нужна — её пишут в дополнение к SCM-куки, а не вместо. **Не путать** с ней основной механизм.

### 3.3 PON spare — только для обычных причин

`qpnp-power-on.c` (и mainline `qcom-pon.c`) пишет в `PON_SOFT_RB_SPARE` (база PON + `0x8F`, для pm8916-поколения — SPMI-адрес `0x88F`) значения вида `recovery`/`bootloader`/`rtc`/`dm-verity` со сдвигом `<<1` (PON gen2/3) или `<<2` (gen1); LK читает обратно `(val & 0xFC) >> 2`. **EDL через этот регистр не передаётся никогда** — ни одно из найденных ядер не пишет туда EDL-значение. Значения в разных поколениях различаются (в downstream-enum recovery=`0x01`, bootloader=`0x02`; в раннем mainline qcom-pon наоборот), поэтому таблицы из интернета о «0x10 = EDL в PON» не имеют отношения к делу.

## 4. Что уже есть в нашем дереве 7.3.1

`linux/drivers/firmware/qcom/qcom_scm.c`:

- `qcom_scm_set_download_mode(scm, dload_mode)` (стр. 552): если DT задал `qcom,dload-mode = <&node offset>` → `qcom_scm_io_rmw(dload_mode_addr, QCOM_DLOAD_MASK, FIELD_PREP(...))` (через SCM IO), иначе SCM-вызов `BOOT_SET_DLOAD_MODE`, иначе ошибка «No available mechanism».
- `QCOM_DLOAD_MASK = GENMASK(5, 4)` (стр. 141) — **биты 4–5**, значения `NODUMP=0 / FULLDUMP=1 / MINIDUMP=2 / BOTHDUMP=3` → в регистре `0x00/0x10/0x20/0x30`. Совпадает с аппаратной семантикой downstream. **Бит 0 (EDL) в маску не входит**, и RMW его сохраняет (`new = (old & ~mask) | (val & mask)`).
- `module_param_cb(download_mode, ...)` (стр. 2749) → `/sys/module/qcom_scm/parameters/download_mode`, значения off/full/mini/full,mini. Работает и как kernel cmdline (`qcom_scm.download_mode=`).
- `qcom_scm_find_dload_address()` (стр. 2056): парсит `qcom,dload-mode = <&phandle offset>` из узла scm.
- `qcom_scm_io_readl/io_writel` **экспортированы** (стр. 1147/1162) — можно пользоваться из отдельного модуля.
- `qcom_scm_shutdown()` (стр. 2951) на чистом рестарте принудительно возвращает `NODUMP` — но маской `GENMASK(5,4)`, т.е. **чистит только dump-биты, бит 0 EDL остаётся**. Это удобно: установленная EDL-куки выживает через штатный `reboot`.

DTS: `sm6225.dtsi` наследует `sm6115.dtsi` (khaje — производная bengal); `tcsr_regs: syscon@3c0000` (reg `0x003c0000…0x40000`), значит `tcsr_regs + 0x13000 = 0x3D3000` — ровно downstream-адрес. Узел `scm` в sm6115.dtsi свойства `qcom,dload-mode` **не имеет** (у sm8450/sm8350/monaco в mainline есть `qcom,dload-mode = <&tcsr 0x13000>` — образец оформления).

Сброс: `drivers/watchdog/qcom-wdt.c` restart = bite watchdog'а c `mdelay(150)` — тёплый сброс, для куки не важно, чем именно он сделан (сток делает PS_HOLD); важно, что питание не теряется.

## 5. План воспроизведения

### 5.1 DTS

В `linux/arch/arm64/boot/dts/qcom/sm6115.dtsi` в узел scm:

```dts
&scm {
	qcom,dload-mode = <&tcsr_regs 0x13000>;   /* TCSR BOOT_MISC_DETECT = 0x3D3000 */
};
```

(Как в mainline sm8450.dtsi:480. Можно и в `sm6225-chuwi-aupad.dts` — метки `&scm`/`&tcsr_regs` видны на уровне платы.)

### 5.2 Патч ядра: параметр `edl`

Эскиз (дополнение к `qcom_scm.c`, рядом с остальными параметрами):

```c
#define QCOM_DLOAD_EDL		BIT(0)   /* рядом с QCOM_DLOAD_* defines */

static bool edl_mode;

static int get_edl_mode(char *buffer, const struct kernel_param *kp)
{
	return sysfs_emit(buffer, "%d\n", edl_mode);
}

static int set_edl_mode(const char *val, const struct kernel_param *kp)
{
	struct qcom_scm *scm;
	bool tmp;
	int ret;

	ret = kstrtobool(val, &tmp);
	if (ret)
		return ret;

	edl_mode = tmp;
	/* Pairs with smp_store_release() in qcom_scm_probe(). */
	scm = smp_load_acquire(&__scm);
	if (!scm)
		return 0;
	if (scm->dload_mode_addr)
		ret = qcom_scm_io_rmw(scm->dload_mode_addr, QCOM_DLOAD_EDL,
				      edl_mode ? QCOM_DLOAD_EDL : 0);
	else
		ret = __qcom_scm_set_dload_mode(scm->dev, edl_mode);
	return ret;
}

static const struct kernel_param_ops edl_mode_param_ops = {
	.get = get_edl_mode,
	.set = set_edl_mode,
};
module_param_cb(edl, &edl_mode_param_ops, NULL, 0644);
```

Примечания:
- `qcom_scm_shutdown()` не трогаем — он чистит только dump-биты и оставляет EDL-бит установленным до самого сброса.
- В `qcom_scm_probe()` после `qcom_scm_set_download_mode(scm, download_mode)` можно применить и `edl_mode` (для cmdline `qcom_scm.edl=1`) — опционально.
- Альтернатива без правки ядра: out-of-tree модуль на экспортированных `qcom_scm_io_readl/io_writel` (читать `0x3D3000`, установить бит 0, записать). Минус — дублирование логики и хардкод адреса.

### 5.3 Использование

```sh
echo 1 > /sys/module/qcom_scm/parameters/edl   # куки пишется сразу, через SCM
reboot -f                                      # busybox: тёплый сброс (WDT bite)
# на хосте появляется 05c6:9008 — дальше штатный firehose
```

Возврат: `echo 0 > .../edl` перед обычной перезагрузкой; выход из EDL — как в PORT.md: SRST через EUD SWD (`tools/ocd/srst`), оттуда и сейчас надёжно выходим.

### 5.4 Проверка и отладка

1. Собрать ядро + dtb, залить test B штатным путём.
2. На планшете: `cat /sys/module/qcom_scm/parameters/edl` → `0`; `echo 1` → снова `cat` (и `dmesg` — при ошибке SCM будет «failed to set download mode» или «No available mechanism», видно по EUD-консоли).
3. `reboot -f` → на хосте `lsusb` должен показать `05c6:9008` (или `900e`).
4. Если 9008 нет — сначала проверить, что `dload_mode_addr` реально получен (нет сообщений об ошибке probe), затем попробовать путь без DT-свойства (SCM `BOOT_SET_DLOAD_MODE`), затем — прямую запись `0x01` (не RMW) `0x3D3000` из отладочного модуля: возможно, XBL Khaje смотрит на полный байт, а не только на бит 0.

### 5.5 Риски и неопределённости

- **SCM_SVC_IO доступность** на TZ divar/SM6225 — предполагаем доступной (сток пользуется тем же сервисом), подтверждается только тестом.
- **WDT-сброс вместо PS_HOLD**: куки документированно переживает reset, mainline sm8450 использует ту же связку (dload-mode + WDT restart) для dump-режимов. Риск низкий.
- **Состояние после входа в EDL**: по PORT.md из EDL и `power reset`, и power cycle возвращают в EDL — это поведение не зависит от способа входа; выход через SRST остаётся без изменений.
- Из userspace напрямую регистр записать нельзя: регион занят syscon-драйвером (`IO_STRICT_DEVMEM`), и сток пишет его только через SCM — прямая запись из EL1, вероятно, отсекается XPU/TZ.

## 6. Мини-справка: где что лежит

| Что | Где | Значение |
|---|---|---|
| Куки EDL/dump | TCSR `BOOT_MISC_DETECT` = `0x3D3000` (`tcsr_regs+0x13000`) | `0x01` = EDL, `0x10/0x20` = full/mini dump |
| Причины reboot (не EDL) | PON `SOFT_RB_SPARE` = PON-база + `0x8F` (SPMI) | recovery/bootloader/rtc, сдвиг <<1 (gen2/3) или <<2 (gen1) |
| IMEM emergency-магия | `qcom,msm-imem-emergency_download_mode` | `0x322A4F99/0xC67E4350/0x77777777` — legacy (msm8974/8994) |
| Вызов записи | SCM `SVC_IO=5` cmd 2 (writel) или `SVC_BOOT=1` cmd 0x10 | только через TrustZone |
| Наш параметр (после патча) | `/sys/module/qcom_scm/parameters/edl` | `echo 1 && reboot -f` |

## 7. Источники

- AOSP: [adb client commandline.cpp](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/client/commandline.cpp), [daemon/services.cpp](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/daemon/services.cpp), [system/core/reboot/reboot.c](https://android.googlesource.com/platform/system/core/+/refs/heads/main/reboot/reboot.c), [init/reboot_utils.cpp](https://android.googlesource.com/platform/system/core/+/refs/heads/main/init/reboot_utils.cpp)
- Downstream: [CodeLinaro msm-5.4 msm-poweroff.c / qcom-dload-mode.c / qcom_scm.c](https://git.codelinaro.org/clo/la/kernel/msm-5.4), [bengal.dtsi (Xiaomi SM6115)](https://github.com/greenforce-project/kernel_xiaomi_citrus_sm6115/blob/qti-perf/arch/arm64/boot/dts/vendor/qcom/bengal.dtsi), [LK reboot.h/reboot.c](https://git.codelinaro.org/clo/la/kernel/lk/-/blob/LA.UM.10.6.2.c26/platform/msm_shared/reboot.h)
- Реверс PBL: [Aleph Security, Qualcomm EDL part 1 (msm8974)](https://alephsecurity.com/2018/01/22/qualcomm-edl-1/), [Quarkslab, Analysis of the Qualcomm secure boot chains (msm8994)](https://blog.quarkslab.com/analysis-of-qualcomm-secure-boot-chains.html), [разбор XBL boot_dload](https://www.iliuqi.com/archives/android-stability-004)
- Mainline: `drivers/firmware/qcom/qcom_scm.c`, `drivers/power/reset/qcom-pon.c`, `drivers/watchdog/qcom-wdt.c`, `arch/arm64/boot/dts/qcom/sm8450.dtsi` (образец `qcom,dload-mode`) — локальное дерево 7.3.1
- Документация Qualcomm: [Boot architecture (EDL как emergency-путь PBL)](https://dragonwingdocs.qualcomm.com/System/Boot/boot-architecture), [Cold boot flow](https://docs.qualcomm.com/doc/80-88500-4/topic/9_Cold_boot_flow.html)
- Локально: `docs/PORT.md` (строки 66, 551–553 — EDL-практики планшета), `linux/arch/arm64/boot/dts/qcom/sm6115.dtsi`, `sm6225.dtsi`
