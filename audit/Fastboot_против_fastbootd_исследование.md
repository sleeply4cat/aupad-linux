# Fastboot против fastbootd: почему стоковый fastboot не пишет разделы

**Вопрос.** На CHUWI AuPad (SM6225 «khaje», плата UNC6851 CW108-WW) стоковый режим fastboot
не записывает разделы, а fastbootd (userspace fastboot из recovery) пишет. Почему?

**Условия исследования.** Планшет не трогался. Всё построено на локальных материалах:
бэкап разделов от 2026-11-12 (`~/111/backups/aupad-20261112/`), документация репозитория,
публичные исходники Qualcomm/AOSP и reverse engineering обоих стоковых ABL.

---

## 1. Короткий ответ

Причины разные на разных уровнях, и все они проверены по бинарям:

1. **В слоте a лежит старая сборка ABL, у которой команды `flash`/`erase`/`boot`/`set_active`
   вообще не зарегистрированы** — их нет в списке команд fastboot. Любой `fastboot flash X`
   получает `unknown command`. Код обработки flash в образе скомпилирован, но не подключён.
2. **В слоте b (рабочий ABL, LA.VENDOR.13.2.1.r1) команды зарегистрированы, но CHUWI
   закрыла flash собственным переключателем**: `fastboot flash` до выполнения
   `fastboot oem activate-flash` отвечает `Fastboot flash commands not allowed.`
   Активация печатает `OEM TEMP ENABLE FASTBOOT` и ставит RAM-флаг (сбрасывается
   каждой загрузкой ABL).
3. Поверх флага в `CmdFlash` стоят штатные гейты Qualcomm: lock state
   (`Flashing is not allowed in Lock State`), список критических разделов
   (`Flashing is not allowed for Critical Partitions`), батарея
   (`Warning: battery's capacity is very low`).
4. `fastboot boot` не зарегистрирован ни в одной из двух сборок (в исходнике он за
   `#ifdef ENABLE_BOOT_CMD`, CHUWI его не включает) — это и есть «ABL не даёт
   `fastboot boot`» из docs/PORT.md.
5. Динамические разделы (`system`, `vendor`, `product`, `odm`, …) bootloader-fastboot
   не умеет писать **архитектурно**: их нет в GPT, они лежат внутри `super` (sda6, 8 GiB).
   Это не поломка, а причина существования fastbootd как класса.
6. **fastbootd** — совершенно другая программа: `/system/bin/fastbootd` в ramdisk
   стокового recovery_a, userspace с root, пишет `/dev/block/by-name/*` напрямую и
   умеет super через liblp. Его единственный гейт — `ro.boot.verifiedbootstate != orange`;
   благодаря пропатченному devinfo ABL передаёт `androidboot.verifiedbootstate=orange`
   и `androidboot.vbmeta.device_state=unlocked`, так что fastbootd всё разрешает.

---

## 2. Материалы и метод

| Материал | Что из него взято |
|---|---|
| `~/111/backups/aupad-20261112/abl_a.bin`, `abl_b.bin` | стоковые ABL обоих слотов, полная RE |
| там же `devinfo.bin` | состояние разблокировки (байты 13/14) |
| там же `recovery_a.bin` | распакован ramdisk, найден `fastbootd` |
| там же `partition-map.txt` | раскладка 6 LUN / 88 разделов |
| CLO `clo/kernel-platform-2-0-os/abl/tianocore/edk2`, ветка `uefi.lnx.4.0.c16` | эталонный `QcomModulePkg/Library/FastbootLib/FastbootCmds.c`, `QcomModulePkg.dec`, `DeviceInfo.h` |
| AOSP `platform/system/core`, `fastboot/device/` | гейты fastbootd (`GetDeviceLockStatus`) |
| RE-документация Onyx Boox Note Air5 C (Wayback) | независимая сверка структуры FastbootLib (другой OEM, та же библиотека) |

Разбор бинарей: MBN v8 → LZMA-alone (props `5d`, словарь 16 МБ) → payload
→ UEFI Firmware Volume (`_FVH`) → единственный FFS-файл «LinuxLoader»
→ PE32+ AArch64 (`ImageBase` 0, `.text` raw==RVA) → дизассемблирование
`aarch64-linux-gnu-objdump` + сопоставление с исходником по строкам-литералам.
Все смещения ниже — RVA внутри извлечённого LinuxLoader.efi (для Boox-доки было
«RVA = file offset − 0xb8», у нас PE уже вырезан).

Не путать: `abl_a` payload = 512 200 байт, `abl_b` = 557 256 байт — **это разные сборки**
(см. §4). MD5 payload: `32a8eacb…` / `4d7a286a…`.

---

## 3. Архитектура: два разных «fastboot»

На устройстве есть два несвязанных fastboot-сервера:

| | bootloader fastboot | fastbootd |
|---|---|---|
| Где живёт | внутри ABL (UEFI-приложение LinuxLoader) | `/system/bin/fastbootd` в ramdisk recovery_a |
| Код | Qualcomm QcomModulePkg/Library/FastbootLib (edk2) | AOSP `system/core/fastboot/device` + fs_mgr/liblp |
| Права | UEFI BlockIo/EraseBlock поверх GPT | root в Android, `/dev/block/by-name/*` |
| Динамические разделы | не видит (только GPT) | читает метаданные `super`, пишет внутрь |
| Гейты | свои (см. §5–6) | `GetDeviceLockStatus()`: `ro.boot.verifiedbootstate != "orange"` |

`fastboot reboot fastboot` попадает в fastbootd так: ABL-команда `reboot-fastboot`
(cb 0x48810 в abl_b) пишет в BCB `boot-fastboot`, ABL при загрузке видит это и
грузит recovery с флагом fastbootd. В abl_a соответствующий обработчик тоже есть
(FastbootRegister("reboot-fastboot") — одна из трёх индивидуальных регистраций).

---

## 4. Два разных ABL в слотах

Строка пути сборки в обоих payload'ах указывает на CHUWI-воркспейс:

```
/Data_18T3/wangchenyan/workspace/CW109_UPQ0090010/LA.VENDOR.13.2.1.r1/LINUX/android/
  kernel_platform/bootable/bootloader/edk2/QcomModulePkg/.../LinuxLoader.dll        (abl_a, -user)
  .../out/msm-kernel-bengal-gki/abl-user/...                                        (abl_b)
```

- **abl_a** — сборка эпохи QSSI11: нет ни одной строки-гейта
  («Flashing is not allowed…», «Critical Partitions», `avb_custom_key`),
  команды с двоеточием (`flash:`/`erase:`) отсутствуют — стиль старого списка.
- **abl_b** — сборка эпохи QSSI12: полная таблица команд (см. §6), гейты lock state
  и critical partitions, `flashing unlock/lock/…`.

Какой слот активен: цепочка порта (`ABL → recovery_b → stub+U-Boot`, docs/PORT.md,
«Android-free loop») работает только если активный слот — **b**, иначе ABL грузил бы
recovery_a. Значит *работающий* bootloader — `abl_b`. Проверка без риска:
`fastboot getvar current-slot` в режиме bootloader.

Нестандартная разблокировка из README подтверждается по бэкапу: `devinfo.bin` =
`ANDROID-BOOT!` (magic 13 байт, офф. 0–12), байт 13 = `01` (`is_unlocked`),
байт 14 = `01` (`is_unlock_critical`), байт 15 = 0 (`is_charger_screen_enabled`),
всё остальное — нули. Структура — `DeviceInfo` из `QcomModulePkg/Include/Library/DeviceInfo.h`.

---

## 5. abl_a: fastboot без команд записи

Регистрация команд в FastbootLib: статическая таблица `{имя, обработчик}` +
`FastbootRegister()`, строит связанный список; диспетчер `AcceptCmd` ищет самый
длинный префикс. В abl_a найдено **ровно 4 места вызова** `FastbootRegister`
(true RVA 0x47538): цикл по таблице из 13 записей и 3 индивидуальные.

Полный список команд fastboot в abl_a (16 шт.):

```
oem enable-charger-screen   oem disable-charger-screen   oem off-mode-charge
oem select-display-panel    oem set-hw-fence-value       oem set-gpu-preemption
oem device-info             oem audio-framework
continue                    reboot                       reboot-bootloader
getvar:                     download:
reboot-recovery             reboot-fastboot              snapshot-update
```

- `flash`, `erase`, `boot`, `set_active`, `flashing *` — **не зарегистрированы**.
  При этом машинный код flash-обработчика в образе есть (строки
  `InitMultiThreadEnv successfully, will use thread to flash`, `FLASH`,
  `Partition not found : %s`, `Write Protected` …) — CHUWI просто не включила
  регистрацию.
- Никаких строк-гейтов (`Flashing is not allowed in Lock State` и т.п.) в abl_a нет —
  консистентно со старой редакцией исходника (QSSI11-era; то же наблюдение в RE-доке
  Boox Note Air5 C, где у Android-11 сборки guard-строк тоже нет).
- Следствие: `fastboot flash …` / `fastboot erase …` → `FAIL … unknown command`
  (в AcceptCmd после проверки батареи цикл не находит префикс и срабатывает
  `FastbootFail("unknown command")`, строка в abl_a есть).
- Отсюда же и невозможность штатного `fastboot flashing unlock`: команды нет,
  как и в Boox («no bootloader-unlock command»). Единственный путь — правка devinfo,
  что и описано в README.

Важно: в AcceptCmd есть и батарейный гейт (см. §6.3), но в abl_a он до
не-зарегистрированных команд не имеет значения — отказ всё равно `unknown command`.

---

## 6. abl_b: команды есть, но flash выключена и обложена гейтами

### 6.1. Список команд (статическая таблица, .data @0x68d10, 28 записей)

```
flash: →0x4bde8      erase: →0x4d53c      set_active →0x49588
flashing get_unlock_ability →0x4d9ec      flashing unlock →0x4da44
flashing lock →0x4da94               flashing unlock_critical →0x4dc90
flashing lock_critical →0x4dce0
oem activate-flash →0x4dae4          oem openuart →0x4db28
oem closeuart →0x4db90               oem reboot-edl →0x4dbf8
oem enable-charger-screen            oem disable-charger-screen
oem off-mode-charge                  oem select-display-panel
oem set-hw-fence-value               oem set-gpu-preemption
oem device-info                      oem audio-framework
oem ipc-logging                      oem enable-ipc-logging
oem disable-ipc-logging
continue  reboot  reboot-bootloader  getvar:  download:
```

Четыре CHUWI-специфичных (`oem activate-flash`, `openuart`, `closeuart`,
`reboot-edl`) — фабричные добавки. **`boot` отсутствует** — в исходнике он за
`#ifdef ENABLE_BOOT_CMD`; это и есть «ABL не даёт `fastboot boot`» из PORT.md.

В эталонном исходнике FastbootCmds.c (uefi.lnx.4.0.c16) весь блок записи закрыт
директивами компиляции — выбор за вендором:

```c
#ifdef ENABLE_UPDATE_PARTITIONS_CMDS
      {"flash:", CmdFlash}, {"erase:", CmdErase}, {"set_active", CmdSetActive},
      {"flashing get_unlock_ability", …}, {"flashing unlock", …}, {"flashing lock", …},
#endif
#ifdef ENABLE_DEVICE_CRITICAL_LOCK_UNLOCK_CMDS
      {"flashing unlock_critical", …}, {"flashing lock_critical", …},
#endif
#ifdef ENABLE_BOOT_CMD
      {"boot", CmdBoot},
#endif
```

То есть **две сборки CHUWI = один исходник с разными наборами `#ifdef`**: abl_a — всё
выключено, abl_b — UPDATE_PARTITIONS и CRITICAL_LOCK_UNLOCK включены, BOOT_CMD выключен.

### 6.2. Главный гейт abl_b: «Fastboot flash commands not allowed.»

Первое, что делает `CmdFlash` (RVA 0x4bde8) — проверяет RAM-флаг включения:

```asm
04be08: adrp x22, …; add x22, x22, #0x7d8     ; структура @0x867d8
04be24: strb wzr, [x22, #5]                   ; байт-заглушка = 0
04be38: bl   0x6878                           ; служебная проверка (возвращает 1)
04be3c: tst  w0, #0xff
04be40: b.eq 0x4be68                          ; если 0 — мимо гейта
04be44: ldrb w8, [x22]                        ; флаг @0x867d8
04be48: cbnz w8, 0x4be68                      ; флаг != 0 — мимо гейта
04be4c: adrp x0, …"Fastboot flash commands not allowed. "
04be64: b    <FastbootFail/выход>
```

Флаг в файле = 0 → **при каждом старте fastboot запись запрещена**. Кто его ставит —
обработчик `oem activate-flash` (RVA 0x4dae4):

```asm
04daf8: adrp x0, …" OEM TEMP ENABLE FASTBOOT "
04db00: bl   <печать на экран>
04db04: bl   0x505f8
04db08: adrp x8, …; strb #1, [x8, #2008]      ; флаг @0x867d8 := 1
```

Сам обработчик перед этим что-то проверяет (`bl 0x509c8`, при отказе — выход),
полная семантика не прослежена; слово «TEMP» и RAM-природа флага говорят, что
активация живёт до перезагрузки ABL. Есть признаки одноразового «токена»
(при входе `CmdFlash` обнуляет байт `[x22+5]` и меняет местами указатели в
структуре) — точную механику не восстановил, см. §11.

Дальше по тексту `CmdFlash` стоят штатные гейты Qualcomm (все подтверждены
кросс-ссылками строк на код):

| Строка | RVA строки | Ссылка из кода | Условие |
|---|---|---|---|
| `Invalid partition name` | 0x631b7 | 0x4bf00 | пустое/кривое имя |
| `Flashing of %s is not allowed in %a state` | — | 0x4bfb4 | verified boot state (green/yellow/orange) |
| `Flashing is not allowed in Lock State` | 0x5ffde | 0x4bfdc | `!IsUnlocked()` |
| `Flashing is not allowed for Critical Partitions` | 0x63d2f | 0x4c10c | `!IsUnlockCritical() && IsCriticalPartition()` |
| `No data to flash` | 0x5c364 | 0x4bf34 | пустой download-буфер |

Для `CmdErase` (0x4d53c): `Erase is not allowed in Lock State` (0x4d67c), critical —
та же строка (0x4d52c). Для `CmdSetActive` (0x49588): `Slot Change is not allowed
in Lock State` (0x49658).

Практически: на пропатченном devinfo (`is_unlocked=1`, `is_unlock_critical=1`)
гейты 3–4 проходят; **действующий отказ — гейт №1**, `Fastboot flash commands
not allowed.` Если тесты fastboot flash делались **до** правки devinfo, отказ был
бы `Flashing is not allowed in Lock State`.

### 6.3. Батарейный гейт AcceptCmd

В обоих ABL диспетчер `AcceptCmd` перед раздачей команд содержит (сверено с
исходником, `FastbootCmds.c:3947`):

```c
if (FixedPcdGetBool (EnableBatteryVoltageCheck)) {   // default TRUE, QcomModulePkg.dec:179
    if (IsFirstEraseFlash) {
        if (erase/flash) {
            if (!TargetBatterySocOk (&BatteryVoltage)) {
                DEBUG ((EFI_D_VERBOSE, "fastboot: battery voltage: %d\n", …));
                FastbootFail ("Warning: battery's capacity is very low\n");
```

Особенности, проверенные в бинарях:
- `IsFirstEraseFlash` — static, стартует 0 (байт @0x7b25a в abl_a, в файле 0) и
  **взводится только запросом `getvar:partition-type…`** (в AcceptCmd флаг
  переключается `eor w8, w22, #1; strb` при совпадении префикса).
- Современный клиент fastboot в обычном `fastboot flash` этот getvar **не шлёт**
  (он шлёт `getvar:is-logical:*`), но шлёт в `erase` и `format`. После первого
  `erase`/`format` батарейный гейт взводится и проверяет первую же flash/erase.
- `TargetBatterySocOk` (в abl_a @0x1cc00) ходит в протокол ChargerEx
  (`gChargerExProtocolGuid = 6edc8a6d-2663-43cd-90ff-4621ffd10df5`,
  QcomModulePkg.dec:120), читает напряжение и порог; при
  «напряжение < порог» печатает `Error battery voltage: %d Requireed voltage: %d,
  can flash: %d` и возвращает false → flash/erase получают
  `FAILED (remote: 'Warning: battery's capacity is very low')`.

### 6.4. Параллельный download-flash

В AcceptCmd перед гейтами стоит блок parallel-download-flash: если прошлый flash
завершился ошибкой, следующий `flash`/`download` получает `Error: Last flash failed:
%r` (в c16-исходнике так; в abl_a строка отсутствует, в abl_b — блок проверен по
строкам `Failed to creat event for waiting flash completely` и
`Failed to set timer for waiting flash completely`). Т.е. одна неудачная прошивка
отравляет следующие команды до переподключения — ещё одна причина «fastboot
«не пишет»: после первого сбоя всё последующее отклоняется кэшем результата.

---

## 7. Динамические разделы: чего bootloader-fastboot не может в принципе

Из partition-map.txt: GPT содержит `super` (sda6, 8 GiB), но **не содержит**
`system`/`vendor`/`product`/`odm` — это logical partitions внутри метаданных `super`.
Bootloader-fastboot ищет имя только в GPT (`Partition not found : %s` — строка есть
в обоих ABL). Поэтому:

- `fastboot flash system …` в режиме bootloader невозможен независимо от
  флагов/разблокировки — так задумано. Именно ради этого Google и завёл fastbootd.
- `fastboot flash boot/dtbo/vbmeta/recovery/modem …` — физические разделы, они в GPT
  есть; их flash-путь заблокирован только гейтами §6.2–6.3.
- fastbootd в recovery шлёт `getvar:is-logical:<имя>` и для logical-разделов делает
  `resize2`/запись через liblp (строки в распакованном fastbootd:
  `Could not create logical partition`, `Could not open super partition`,
  `create-logical-partition`, `delete-logical-partition`, …).

---

## 8. Почему fastbootd пишет

`recovery_a.bin` (100 МБ, boot image v4: kernel 0, ramdisk LZ4-legacy 14.3 МБ →
30.7 МБ cpio) содержит **`/system/bin/fastbootd`** (AArch64 PIE) — проверено
распаковкой ramdisk из бэкапа. Это AOSP `system/core/fastboot/device`:

- полный протокол: `flash`, `erase`, `set_active`, `boot` (для GSI),
  `create/delete/resize-logical-partition`, `fetch`, `snapshot-update …`;
- пишет `/dev/block/by-name/*` напрямую (root в recovery), для logical-разделов —
  через метаданные `super`;
- единственный гейт записи — `GetDeviceLockStatus()`
  (system/core/fastboot/device/utility.cpp:197):

```cpp
bool GetDeviceLockStatus() {
    return android::base::GetProperty("ro.boot.verifiedbootstate", "") != "orange";
}
```

`flash`/`erase`/`download`/`set_active` отказывают только при locked
(`Flashing is not allowed on locked devices` и т.п. — строки есть в бинаре fastbootd).

Состояние fastbootd получает из kernel cmdline, который формирует ABL: в обоих ABL
есть строки `androidboot.verifiedbootstate` и `androidboot.vbmeta.device_state`.
Пропатченный devinfo (`is_unlocked=1`) делает ABL «unlocked» → ABL передаёт
`verifiedbootstate=orange`, `vbmeta.device_state=unlocked` → fastbootd разрешает всё.
Батарейного гейта, переключателя activate-flash и списка критических разделов
в fastbootd нет — он вообще не разговаривает с ABL о правах.

Косвенное подтверждение: пользователям этой же платформы для записи из
bootloader-fastboot известен путь `oem activate-flash`; а fastbootd-путь —
стандартный для всех Android 10+.

---

## 9. Сводная таблица гейтов

| Гейт | abl_a (слот a) | abl_b (слот b, работает) | fastbootd |
|---|---|---|---|
| Команда `flash` зарегистрирована | нет | да (`#ifdef ENABLE_UPDATE_PARTITIONS_CMDS`) | да |
| Команда `boot` зарегистрирована | нет | нет (`ENABLE_BOOT_CMD` off) | да |
| Флаг активации записи | — | **`oem activate-flash`** («Fastboot flash commands not allowed.») | — |
| Lock state | — | `Flashing is not allowed in Lock State` | `ro.boot.verifiedbootstate != orange` |
| Критические разделы | — | `… for Critical Partitions` | нет |
| Батарея | есть, до `unknown command` не доходит | `Warning: battery's capacity is very low` (после `getvar:partition-type`) | нет |
| `system`/`vendor`/… | нет в GPT | нет в GPT | пишет внутрь `super` через liblp |
| Кэш «Last flash failed» | нет | есть (parallel-download-flash) | нет |

---

## 10. Ответ

- «Стоковый fastboot не пишет» — не поломка UFS и не AVB. В рабочем ABL (слот b)
  команда `flash` зарегистрирована, но CHUWI закрыла её фабричным переключателем:
  без `fastboot oem activate-flash` любой `fastboot flash` →
  `FAILED (remote: 'Fastboot flash commands not allowed.')`. В запасном ABL (слот a)
  команды записи вообще не зарегистрированы → `unknown command`. `fastboot boot`
  выключен в обеих сборках (флаг `ENABLE_BOOT_CMD`), что согласуется с
  docs/PORT.md («ABL не даёт fastboot boot»).
- «fastbootd пишет» — потому что fastbootd это не «тот же fastboot, но из recovery»,
  а отдельная userspace-программа с root: пишет блочные устройства напрямую, умеет
  `super`, и её единственная проверка (`verifiedbootstate != orange`) проходит
  из-за пропатченного devinfo. Она не зависит ни от одного из ABL-гейтов.
- Для динамических разделов (`system`, `vendor`, `product`) bootloader-fastboot
  бесполезен в принципе — только fastbootd.

---

## 11. Как проверить без риска (следующая сессия fastboot)

1. `fastboot getvar all` — зафиксировать `current-slot` (какой ABL работает),
   `max-download-size`, `battery-voltage`, `unlocked`, `secure`.
2. `fastboot flash boot <img>` → записать **точный** текст FAIL. Ожидаемые варианты:
   - `unknown command` → работает ABL_a (или флеш-регистрация отсутствует);
   - `Fastboot flash commands not allowed.` → ABL_b, флаг выключен (ожидаемо);
   - `Flashing is not allowed in Lock State` → devinfo не пропатчен;
   - `Warning: battery's capacity is very low` → взведён батарейный гейт
     (обычно после `erase`/`format`).
3. `fastboot oem activate-flash` → на экране должно появиться
   `OEM TEMP ENABLE FASTBOOT`; затем повторить `fastboot flash boot <img>`
   (безопасный тест: писать бэкап `boot_b.bin` обратно в `boot_b`).
4. `fastboot oem device-info` — собственный вывод ABL о состоянии блокировки.
5. Сравнить `fastboot getvar max-download-size` bootloader'а и fastbootd.
6. Отдельно отметить поведение после одного неудачного flash (кэш «Last flash
   failed») — переподключить USB и повторить.

## 12. Открытые вопросы

- Точная семантика «TEMP»-токена `oem activate-flash`: одноразовый ли это допуск
  (одна flash-команда на активацию) и что проверяет внутренний гейт самого
  обработчика (`bl 0x509c8`). Статически не восстановлено.
- Внутренний порог напряжения в `TargetBatterySocOk` — не извлечён (зависит от
  ChargerLib; строка `Requireed voltage: %d` печатает его в DEBUG-логе ABL).
- Активный слот выведен косвенно (stub живёт в recovery_b); прямая проверка —
  `getvar current-slot`.
- GPT-дампы в бэкапе (`gpt-sd*.bin`) содержат только protective MBR — атрибуты
  разделов (successful/unbootable биты слотов) не видны.

## 13. Источники

- Бэкап планшета 2026-11-12: `~/111/backups/aupad-20261112/` (abl_a/abl_b, devinfo,
  recovery_a, partition-map.txt).
- Qualcomm ABL QcomModulePkg (эталон для сопоставления), CLO
  [`clo/kernel-platform-2-0-os/abl/tianocore/edk2`, `uefi.lnx.4.0.c16`](https://git.codelinaro.org/clo/kernel-platform-2-0-os/abl/tianocore/edk2):
  `FastbootLib/FastbootCmds.c` (#ifdef-флаги, AcceptCmd, батарейный гейт),
  `QcomModulePkg.dec` (`EnableBatteryVoltageCheck|TRUE`, `gChargerExProtocolGuid`),
  `Include/Library/DeviceInfo.h` (структура devinfo).
- AOSP fastbootd: `platform/system/core`, `fastboot/device/utility.cpp`
  (`GetDeviceLockStatus` → `ro.boot.verifiedbootstate`), `fastboot/device/commands.cpp`
  (гейты flash/erase/download/set_active); клиент `platform/system/core/fastboot/fastboot.cpp`
  (`getvar:partition-type` только в erase/format).
- RE-документация ABL другого устройства (та же FastbootLib), Onyx Boox Note Air5 C,
  [архивная копия страницы FastbootLib](http://web.archive.org/web/20260921154547/https://overtone.codeberg.page/onyx-boox-note-air5-c/abl/fastboot.html):
  регистрация через cmd_list + FastbootRegister, «no bootloader-unlock command»,
  отсутствие QSSI12 guard-строк в Android-11 сборках.
- docs/PORT.md этого репозитория: «ABL refuses fastboot boot and fastboot flash»
  (стр. «Boot / test loop»), нестандартная разблокировка, цепочка загрузки.
