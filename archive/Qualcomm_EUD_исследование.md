# Qualcomm EUD: исследование реализаций CTRL, SWD, JTAG, TRACE и COM

**Дата актуализации:** 11 ноября 2026 года  
**Предмет:** открытые и OEM-реализации Qualcomm Embedded USB Debug/Debugger, их фактическая готовность, применение в связанных проектах и возможности самостоятельной интеграции.  
**Основные источники:** исходный код `quic/eud`, основной OpenOCD, `linux-msm/openocd`, Qualcomm CodeLinaro OpenOCD, Linux CoreSight, OpenCSD, OEM/downstream-ядра, публичные журналы устройств и практические эксперименты.

## 1. Краткий вывод

EUD нельзя считать одним полностью готовым открытым инструментом с пятью одинаково поддерживаемыми функциями. Аппаратный блок и библиотека описывают CTRL, SWD, JTAG, TRACE и COM, но степень реализации существенно различается:

| Периферия | Подтверждённое состояние | Практическая оценка |
|---|---|---|
| **CTRL** | Есть рабочие API для состояния, включения периферий, USB attach/detach, charger и reset | **Реализовано**; зависит от доступа к EUD на конкретном устройстве |
| **SWD** | Есть прямой `libusb`-драйвер в основном OpenOCD, конфигурация `eud-swd.cfg` и подтверждённый запуск на Snapdragon 845 | **Единственный завершённый открытый end-to-end сценарий** |
| **JTAG** | Есть низкоуровневые команды TMS/TDI/TDO, bitbang и scan; инициализация отключена, OpenOCD-эксперимент помечен `broken` | **Экспериментально, готовой цепочки нет** |
| **TRACE** | Есть capture API, opcode layer, test client и отдельная активная ветка с исправлениями; Linux умеет представлять EUD как CoreSight dummy sink | **Захват активно дорабатывается; открытая цепочка до декодирования не подтверждена** |
| **COM** | Target-side UART реализован в OEM/downstream-ядрах и регистрируется как `ttyEUD`; host-side публичный API остаётся заглушкой | **Target-side компонент есть, готового открытого host client не найдено** |

Самые важные новые находки исследования:

1. У `quic/eud` существует отдельная ветка [`EUD_Trace_Support`](https://github.com/quic/eud/tree/EUD_Trace_Support), содержащая четыре TRACE-коммита от марта–апреля 2026 года и test client.
2. В основном Linux есть [`arm,coresight-dummy-sink`](https://github.com/torvalds/linux/blob/master/Documentation/devicetree/bindings/arm/arm,coresight-dummy-sink.yaml), явно предназначенный в том числе для Qualcomm EUD. Это позволяет строить путь CoreSight к EUD, но само по себе не захватывает и не декодирует поток.
3. Для COM найден полноценный target-side reference в [OEM-ядре Motorola](https://github.com/MotorolaMobilityLLC/kernel-msm/blob/MMI-S1RFS32.27-25-12/drivers/soc/qcom/eud.c), включая RX/TX, interrupts и регистрацию `ttyEUD`.
4. Проверенные OpenOCD-реализации — upstream, CodeLinaro и историческая QUTS-интеграция — фактически регистрируют только SWD. Наличие JTAG-to-SWD sequence не является поддержкой JTAG transport.

## 2. Методика и критерии доказательств

В отчёте используются следующие категории:

- **Подтверждённый запуск** — опубликован фактический журнал работы, например OpenOCD обнаружил DAP, CPU и запустил GDB server.
- **Рабочий компонент** — код реализует самостоятельную часть системы, но не обязательно весь сценарий. Пример: target-side `ttyEUD`.
- **Экспериментальный код** — присутствуют низкоуровневые операции или тесты, но инициализация, интеграция либо проверка не завершены.
- **Активная незавершённая ветка** — существуют новые коммиты и исправления, но предупреждения и функциональные пробелы остаются.
- **Потенциально совместимый проект** — проект может обработать данные после дополнительного адаптера, но прямой поддержки EUD не имеет. Пример: OpenCSD.
- **Упоминание без реализации** — название функции, function pointer или запись в README не подтверждают работающий сценарий.

Отсутствие найденной реализации означает «не обнаружено в проверенных публичных источниках», а не доказательство того, что закрытой OEM- или внутренней Qualcomm-реализации не существует.

## 3. Что такое EUD и чем он отличается от EDL

**Qualcomm EUD — Embedded USB Debug/Debugger.** Это встроенный отладочный блок, связанный с USB и внутренними debug/trace ресурсами SoC. В описании Qualcomm перечислены CTRL, SWD, JTAG, TRACE и COM: [README `quic/eud`](https://github.com/quic/eud#readme).

EUD не следует путать с **EDL — Emergency Download Mode**:

- EDL прежде всего связан с загрузкой, прошивкой и recovery;
- EUD предоставляет отладочные интерфейсы, доступ к DAP, последовательный канал и trace transport;
- появление устройства Qualcomm в EDL не означает доступность EUD.

Практическое введение и подтверждённый запуск SWD опубликованы Linaro: [The hidden JTAG in your Qualcomm/Snapdragon device’s USB port](https://www.linaro.org/blog/hidden-jtag-qualcomm-snapdragon-usb/).

## 4. USB-устройства и идентификаторы

Qualcomm VID: **`0x05c6`**.

| Функция | PID | Назначение |
|---|---:|---|
| CTRL | `0x9501` | Управление EUD, включение периферий, attach/detach, charger, reset |
| TRACE | `0x9502` | Передача ATB/CoreSight trace данных по USB |
| JTAG | `0x9503` | TAP, TMS/TDI/TDO, scan operations |
| SWD | `0x9504` | Доступ к ARM Debug Access Port по Serial Wire Debug |
| COM | `0x9505` | Пакетный последовательный канал с execution environments/UART |

Источники:

- PID и типы устройств распознаются Linux/libusb scanner в [`src/usb.cpp`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/src/usb.cpp).
- Имена Windows-устройств и PID определены в [`inc/device_manager_defines.h`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/inc/device_manager_defines.h).
- Основной OpenOCD использует VID `0x05c6`, CTRL PID `0x9501`, SWD PID `0x9504`, OUT endpoint `0x02` и IN endpoint `0x81`: [`src/jtag/drivers/eud.c`](https://github.com/openocd-org/openocd/blob/master/src/jtag/drivers/eud.c).

USB scanning и generic bulk transfers в `libeud` образуют пригодную основу для самостоятельных COM/JTAG/TRACE clients, но наличие общего `libusb_bulk_transfer()` не реализует протокол конкретной периферии.

## 5. Зависимость от платформы и debug policy

Доступность EUD определяется не только host software. Необходимы или могут влиять:

- поддержка конкретным SoC;
- корректный Device Tree;
- EUD enable registers;
- USB PHY и USB role switch;
- QFPROM/fuses;
- secure EUD и обращения через SCM/TrustZone;
- OEM-signed debug policy;
- состояние bootloader и USB gadget/fastboot;
- права на настройку CoreSight и DAP.

В основном Linux драйвер [`drivers/usb/misc/qcom_eud.c`](https://github.com/torvalds/linux/blob/master/drivers/usb/misc/qcom_eud.c):

- предоставляет sysfs attribute `enable`;
- записывает secure mode-manager register через `qcom_scm_io_writel()`;
- управляет `EUD_REG_CSR_EUD_EN`;
- переключает USB role;
- обрабатывает attach/detach и safe-mode events.

Патчсет января 2026 года [Improve Qualcomm EUD driver and platform support](https://lwn.net/Articles/1056174/) расширял поддержку PHY, multi-port и role switching. В описании заявлена проверка OpenOCD connectivity на Dragonwing Q6/RB3 Gen2. Это подтверждение платформенной работы над enable path и SWD, но не доказательство готовности JTAG, TRACE или COM.

По данным Linaro, на production-устройствах EUD может быть отключён fuses или production signing, а OEM signed debug policy способна изменять это поведение. Даже обнаруженный DT node не гарантирует, что аппаратный блок разрешено включить.

## 6. CTRL

### 6.1. Реализованные операции

В [`inc/ctl_api.h`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/inc/ctl_api.h) и [`src/ctl_api.cpp`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/src/ctl_api.cpp) присутствуют:

```c
eud_get_version()
eud_get_ctl_status()
eud_get_ctl_status_string()
eud_msm_reset()
eud_msm_assert_reset()
eud_msm_deassert_reset()
eud_enable_charger()
eud_disable_charger()
eud_spoof_attach()
eud_spoof_detach()
eud_connect_usb()
eud_disconnect_usb()
eud_ctl_assert_srst()
eud_ctl_check_srst_status()
eud_ctl_assert_trst()
```

CTRL status содержит биты включения `TRACE_PERIPH_EN`, `JTAG_PERIPH_EN`, `COM_PERIPH_EN` и `SWD_PERIPH_EN`.

Generic initialization выбирает наборы set/clear bits для JTAG, SWD, COM и TRACE, записывает их через CTRL и затем открывает соответствующее USB-устройство. Поэтому CTRL является общей точкой включения остальных функций.

### 6.2. Ограничения

- Успешная запись CTRL не доказывает, что последующий протокол периферии реализован на host.
- В основном OpenOCD CTRL используется непосредственно для включения SWD; полный набор API `libeud` там не используется.
- На secure/production платформах enable path может завершаться ошибкой SCM или аппаратным reset.

**Классификация:** рабочий компонент с конкретными открытыми реализациями.

## 7. SWD

### 7.1. Основной OpenOCD

В upstream OpenOCD драйвер [`src/jtag/drivers/eud.c`](https://github.com/openocd-org/openocd/blob/master/src/jtag/drivers/eud.c) реализован напрямую через `libusb`, без зависимости от `libeud`.

Реализация включает:

- открытие CTRL и SWD USB functions;
- включение SWD через CTRL set/clear commands;
- 32-byte hardware FIFOs в обоих направлениях;
- пакетирование SWD transfers;
- обработку ACK, WAIT timeout, parity error и command counter;
- retries и восстановление;
- JTAG-to-SWD, line reset и другие switch sequences;
- trailing idle clocks;
- reset через bitbang.

Ключевая регистрация:

```c
struct adapter_driver eud_adapter_driver = {
    .name = "eud",
    .transport_ids = TRANSPORT_SWD,
    .transport_preferred_id = TRANSPORT_SWD,
    /* ... */
    .swd_ops = &eud_swd_driver,
};
```

Конфигурация [`tcl/interface/eud-swd.cfg`](https://github.com/openocd-org/openocd/blob/master/tcl/interface/eud-swd.cfg):

```tcl
adapter driver eud
transport select swd
```

Следовательно, `JTAG_TO_SWD` в коде — лишь переключение DAP в SWD mode. Он не добавляет JTAG transport.

### 7.2. История upstream-интеграции

Проверенные коммиты:

- [`d06edabdcdad`](https://github.com/openocd-org/openocd/commit/d06edabdcdad9c4ed5d66102311c89c5c44e4e87) — minimal SWD-over-EUD;
- [`0e6effa88373`](https://github.com/openocd-org/openocd/commit/0e6effa88373) — batch SWD transfers;
- [`ddb476bc90c8`](https://github.com/openocd-org/openocd/commit/ddb476bc90c8) — обработка whole SWD status word;
- [`d3ebb8d2b9ad`](https://github.com/openocd-org/openocd/commit/d3ebb8d2b9ad) — trailing idle clocks.

OpenOCD Gerrit change [9773](https://review.openocd.org/c/openocd/+/9773), `adapter/eud: Introduce a minimal implementation for SWD-over-EUD`, имеет статус MERGED; в обсуждении описаны 32-byte FIFOs, последовательная обработка opcodes и остановка на undefined opcode/NOP. Предложение учитывать TRACE/JTAG относилось к возможному будущему расширению и USB dumps, а не к уже реализованной поддержке.

### 7.3. Подтверждённый практический запуск

[Linaro](https://www.linaro.org/blog/hidden-jtag-qualcomm-snapdragon-usb/) опубликовала запуск на Snapdragon 845, в журнале которого видны:

```text
Info : SWD DPIDR 0x5ba02477
Info : QCOM.cpu0: hardware has 6 breakpoints, 4 watchpoints
Info : [QCOM.cpu0] Examination succeed
Info : [QCOM.cpu0] starting gdb server on 3333
QCOM.cpu0 halted in AArch64 state due to debug-request
```

Это подтверждает не только USB enumeration, но и DAP discovery, CPU examination, halt и запуск GDB server.

Для SDM845/U-Boot в `linux-msm/openocd` приводилась последовательность:

```sh
mw.l 0x88e1014 1
run fastboot
```

Также требовался patch, чтобы USB gadget/fastboot не выключал USB controller. Эти адреса и последовательность SoC-specific и не должны переноситься на другие устройства без проверки.

### 7.4. Qualcomm CodeLinaro OpenOCD

Репозиторий: [Qualcomm CodeLinaro OpenOCD](https://git.codelinaro.org/clo/la/openocd-org/openocd), ветка `qcom_changes`.

Исследованный HEAD:

```text
532b9af9e3bde361add988273a9599c53d3cfd8a
2026-09-25
openocd: OpenOCD 2.0.7 release updates
```

В [`src/jtag/drivers/eud.c`](https://git.codelinaro.org/clo/la/openocd-org/openocd/-/blob/532b9af9e3bde361add988273a9599c53d3cfd8a/src/jtag/drivers/eud.c):

- transport list содержит только `swd`;
- `.config_trace = NULL` и `.poll_trace = NULL`;
- присутствуют CTRL spoof attach/detach;
- есть ADIv6 reset handling и SWD retry logic.

Конфигурации:

- [`tcl/interface/eud.cfg`](https://git.codelinaro.org/clo/la/openocd-org/openocd/-/blob/532b9af9e3bde361add988273a9599c53d3cfd8a/tcl/interface/eud.cfg);
- [`tcl/target/qualcomm/qcs6490.cfg`](https://git.codelinaro.org/clo/la/openocd-org/openocd/-/blob/532b9af9e3bde361add988273a9599c53d3cfd8a/tcl/target/qualcomm/qcs6490.cfg);
- [`tcl/target/qualcomm/qcs9100.cfg`](https://git.codelinaro.org/clo/la/openocd-org/openocd/-/blob/532b9af9e3bde361add988273a9599c53d3cfd8a/tcl/target/qualcomm/qcs9100.cfg).

Обе target-конфигурации описывают EUD как SWD-only.

**Классификация SWD:** подтверждённый, практически применимый открытый сценарий.

## 8. TRACE

### 8.1. Что реализовано в основном `quic/eud`

TRACE peripheral связан с ATB — ARM Advanced Trace Bus. EUD может выступать внешней точкой вывода CoreSight traffic по USB, но USB capture — только одна часть полного сценария.

В [`inc/trc_api.h`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/inc/trc_api.h) основной ветки прямо указано:

> Trace Peripheral not completed and is under develepment

Предлагаемая последовательность включает:

```c
eud_initialize_device_trace()
eud_trace_set_timeout_ms()
eud_trace_set_transfer_length()
eud_trace_set_chunk_sizes()
eud_trace_set_output_dir()
eud_start_tracing()
eud_close_trace()
```

Capture mode не реализован:

```c
// EUD_TraceSetCaptureMode not yet implemented
```

В [`inc/trc_eud.h`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/inc/trc_eud.h) определены команды:

```c
#define TRC_CMD_NOP         0x0
#define TRC_CMD_FLUSH       0x1
#define TRC_CMD_TRNS_LEN    0x2
#define TRC_CMD_TRNS_TMOUT  0x3
#define TRC_CMD_TOSS        0x4
#define TRC_CMD_KEEP        0x5
#define TRC_CMD_PERIPH_RST  0x6
```

Параметры по умолчанию и ограничения:

```c
TRACE_DEFAULT_TRNS_TMOUT          0x00FFFFFF
TRACE_DEFAULT_TRANSACTION_LENGTH  100
TRACE_MAX_TRANSLEN_SIZE           0x0000FFFF
TRACE_MIN_TRANSLEN_SIZE           2
```

Transfer length не должен быть кратен 128.

По комментариям API:

- после reset peripheral находится в `trace_toss` mode;
- `TRACE_KEEP` начинает передавать ATB data host;
- `TRACE_FLUSH` инициирует ATB flush;
- timeout может завершать transfer zero-length или partial packet;
- `TRACE_PERIPH_RST` очищает buffers и восстанавливает параметры.

### 8.2. Capture в `main`

В [`src/trc_api.cpp`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/src/trc_api.cpp):

1. `eud_trace_config()` отправляет timeout;
2. выполняется чтение существующего буфера;
3. задаётся transfer length;
4. `eud_start_tracing()` отправляет `trace_keep()`;
5. USB data записываются в `Trace.bin`.

В старом `main` обнаружен дефект:

```cpp
for (uint8_t i = 2;
     i < trace_handle_p->current_trace_transaction_length_;
     i++)
```

При transaction length больше 255 8-битный индекс может зациклиться или привести к неполной записи.

Кроме того, старый код отбрасывал данные с `tracedata[0] == 0xFF`, а остальные записывал начиная с байта 2. Это означает пропуск ATID/length metadata и одновременно показывает: результат представляет собой обработанный capture ATB-данных, а не настройку CoreSight и не декодирование ETM.

### 8.3. Ветка `EUD_Trace_Support`

HEAD исследованной ветки:

```text
ae307548d8a611f53bfd281a67b03b7fd1d8d727
```

История:

| Коммит | Дата | Содержание |
|---|---|---|
| [`3392e3a5ec52`](https://github.com/quic/eud/commit/3392e3a5ec52) | 24 марта 2026 | Поддержка EUD Trace functionality from third party tools like QUTS; добавлен test application |
| [`99e23c40b8a5`](https://github.com/quic/eud/commit/99e23c40b8a5) | 24 марта 2026 | Изменения, чтобы не копировать ATID и length bytes в trace buffer |
| [`68a0c0cb8304`](https://github.com/quic/eud/commit/68a0c0cb8304) | 3 апреля 2026 | EUD Trace issues fixes; revision update |
| [`ae307548d8a6`](https://github.com/quic/eud/commit/ae307548d8a611f53bfd281a67b03b7fd1d8d727) | 3 апреля 2026 | Handling for buffer overrun error |

[Сравнение `main...EUD_Trace_Support`](https://github.com/quic/eud/compare/main...EUD_Trace_Support): ветка diverged, ahead by 4, behind by 1; изменены восемь файлов:

- `inc/eud_revision.h`;
- `inc/trc_api.h`;
- `inc/trc_eud.h`;
- `inc/usb.h`;
- `src/trc_api.cpp`;
- `src/trc_eud.cpp`;
- `src/usb.cpp`;
- новый `test/test_trace.c`.

Ветка не была обнаружена влитой в `main`.

### 8.4. Новый публичный API и test client

В ветке API принимает буфер вызывающей программы:

```c
eud_trace_device_init(device_id, trns_len, trns_tmout);
eud_trace_device_ready();

eud_trace_device_read(
    trace_buffer,
    bytes_to_read,
    &bytes_read
);

eud_trace_device_close();
```

Источники:

- [`inc/trc_api.h` на HEAD ветки](https://github.com/quic/eud/blob/ae307548d8a611f53bfd281a67b03b7fd1d8d727/inc/trc_api.h);
- [`src/trc_api.cpp` на HEAD ветки](https://github.com/quic/eud/blob/ae307548d8a611f53bfd281a67b03b7fd1d8d727/src/trc_api.cpp);
- [`test/test_trace.c`](https://github.com/quic/eud/blob/ae307548d8a611f53bfd281a67b03b7fd1d8d727/test/test_trace.c).

Test client задаёт:

```c
uint32_t trns_len = 126;
uint32_t trns_tmout = 0x00EE12EA;
```

Он получает device ID, инициализирует TRACE, отправляет KEEP через ready call, ждёт заданную задержку, читает требуемое количество байтов и сохраняет фактически полученные данные в бинарный файл.

Интерфейс test client:

```text
<sleep_delay_ms> <bytes_to_read>
```

Пример, указанный в исходнике:

```text
5000 2048
```

Это standalone test application, а не доказательство интеграции TRACE commands в OpenOCD.

### 8.5. Что исправлено

Старый 8-битный цикл заменён чтением в caller buffer с:

- `size_t buffer_offset`;
- `bytes_remaining`;
- `bytes_to_request`;
- `read_result.bytes_read`;
- накоплением фактически прочитанных данных.

Это устраняет прежнюю проблему длины больше 255 и позволяет стороннему инструменту получить поток через API.

В USB layer добавлен guard buffer для ситуации, когда оставшийся запрошенный размер меньше configured transaction length: чтение выполняется во временный буфер большего размера, чтобы избежать переполнения caller buffer.

### 8.6. Оставшиеся проблемы на HEAD ветки

Предупреждение `Trace Peripheral not completed` осталось в `inc/trc_api.h`; capture mode по-прежнему не реализован.

Дополнительно по исходникам HEAD:

1. **Zero-length successful read не продвигает цикл.** Если `LIBUSB_SUCCESS` и `bytes_read == 0`, `buffer_offset` не меняется, а цикл продолжается. Это может привести к бесконечному ожиданию.
2. **Timeout обрабатывается непоследовательно.** Комментарий USB layer называет timeout с zero/partial data допустимым, но `ReadFromDeviceTrc()` возвращает успех только для `LIBUSB_SUCCESS`; при ошибке вызывается `UsbClose()`.
3. **Guard buffer не сохраняет остаток.** Если USB вернул больше байтов, чем осталось в caller buffer, копируется только запрошенная часть. Остаток не помещается во внутренний carry-over buffer и может быть потерян для непрерывного потока.
4. **Формат выхода требует отдельной проверки.** Хотя промежуточный коммит `99e23c4` заявлял исключение ATID/length, на конечном HEAD `eud_start_tracing()` копирует USB read data непосредственно в выходной buffer. Нельзя автоматически считать результат очищенным CoreSight stream.

Источник по buffer handling: [коммит `ae307548d8a6`](https://github.com/quic/eud/commit/ae307548d8a611f53bfd281a67b03b7fd1d8d727), [`src/usb.cpp`](https://github.com/quic/eud/blob/ae307548d8a611f53bfd281a67b03b7fd1d8d727/src/usb.cpp).

**Классификация:** активная незавершённая ветка с полезным capture API. Назвать её production-ready или подтверждённым CoreSight decode workflow нельзя.

### 8.7. Что означает упоминание QUTS

Сообщение `3392e3a5ec52` говорит о поддержке EUD Trace functionality со стороны third-party tools «like QUTs». Публичный diff при этом показывает изменения `libeud` и test application, а не открытый исходный код QUTS.

Корректная интерпретация: Qualcomm подготавливал API для внешнего потребителя. Это не доказывает наличие открытого QUTS workflow и не заменяет аппаратную проверку.

### 8.8. CodeLinaro `test_trace.c`

В Qualcomm CodeLinaro OpenOCD существует отдельный client:

[`src/jtag/drivers/eud/test/test_trace.c`](https://git.codelinaro.org/clo/la/openocd-org/openocd/-/blob/532b9af9e3bde361add988273a9599c53d3cfd8a/src/jtag/drivers/eud/test/test_trace.c)

В исследованной версии использовались параметры:

```c
uint32_t trns_len = 42;
uint32_t trns_tmout = 0x00EE12EA;
uint32_t on_time = 30;

err = get_device_id_array(arr, &len);
device_id = arr[0];

err = eud_trace_device_init(device_id, trns_len, trns_tmout, on_time);
err = eud_trace_device_read();
err = eud_trace_device_close();
```

Это конкретный test client, но не `.config_trace`/`.poll_trace` integration в OpenOCD. Он не настраивает ETM/ETE/STM и не декодирует результат.

### 8.9. `File_Logging_Support`

Дополнительная ветка [`File_Logging_Support`](https://github.com/quic/eud/tree/File_Logging_Support) содержит все четыре TRACE-коммита и коммит:

```text
3bf523dd29f5bbddf52f2dd8112f9895b59794b6
2026-04-13
Added File logging support
```

[Сравнение с `main`](https://github.com/quic/eud/compare/main...File_Logging_Support): ahead by 5, behind by 1, изменены 14 файлов. Дополнительно появляются `inc/eud_log.h`, `src/eud_log.cpp`, изменения `Makefile.am`, `device_manager.cpp` и `usb.cpp`.

Это инфраструктура логирования поверх TRACE-ветки, а не реализация COM или JTAG.

### 8.10. Target-side CoreSight path к EUD

В Linux существует драйвер [`coresight-dummy.c`](https://github.com/torvalds/linux/blob/master/drivers/hwtracing/coresight/coresight-dummy.c) и binding [`arm,coresight-dummy-sink.yaml`](https://github.com/torvalds/linux/blob/master/Documentation/devicetree/bindings/arm/arm,coresight-dummy-sink.yaml).

Binding прямо называет Qualcomm EUD примером sink, который kernel не имеет права или возможности программировать непосредственно. Dummy driver нужен, чтобы зарегистрировать EUD как CoreSight sink и построить путь:

> Then the trace flow would be transferred to EUD via coresight link of AP processor.

`dummy_sink_enable()` фактически только сообщает `Dummy sink enabled` и возвращает success. Драйвер:

- не управляет USB;
- не читает USB trace;
- не предоставляет host decoder;
- позволяет CoreSight framework учитывать EUD в topology и включать промежуточные links.

`CONFIG_CORESIGHT_DUMMY` в [`drivers/hwtracing/coresight/Kconfig`](https://github.com/torvalds/linux/blob/master/drivers/hwtracing/coresight/Kconfig) описан как поддержка sources/sinks, которые принадлежат и настраиваются другим subsystem, тогда как Linux drivers настраивают остальную часть trace path.

### 8.11. Пример новой SoC-топологии

Патчсет июля 2026 года [Add CoreSight nodes for Qualcomm Shikra SoC](https://lore.jethome.com/lkml/20260723-add-coresight-nodes-for-shikra-v5-0-fd5494471b36@oss.qualcomm.com/T/) добавляет:

- per-core ETM;
- STM;
- TPDM/TPDA;
- funnels;
- ETF и ETR;
- replicators;
- CTCU;
- dummy sources;
- `dummy-eud` sink.

В DT показан путь через replicators к `eud_in`. Это ценный reference для топологии, но патчсет не следует без дополнительной проверки считать доказательством наличия таких nodes в произвольной production-платформе.

### 8.12. Реалистичная интеграционная цепочка

```text
ETM/ETE или STM
        ↓
      funnel
        ↓
  ETF / replicator
        ↓
   EUD ATB sink
        ↓
USB 05c6:9502
        ↓
libeud TRACE capture
        ↓
сохранение сырого потока и разбор ATB/ATID
        ↓
OpenCSD или другой CoreSight decoder
```

Для платформы, где Device Tree уже содержит необходимые nodes, target-side активация концептуально может выглядеть так:

```sh
CS=/sys/bus/coresight/devices
ls "$CS"

# Условные имена: сначала определить реальные на конкретной системе.
echo 1 > "$CS/dummy_sink0/enable_sink"
echo 1 > "$CS/etm0/enable_source"

# Параллельно на host выполнять EUD TRACE capture.

echo 0 > "$CS/etm0/enable_source"
echo 0 > "$CS/dummy_sink0/enable_sink"
```

Это не универсальная готовая команда. Имена устройств, наличие ETM, права доступа, security state и sink path зависят от платформы. [Документация Linux CoreSight](https://github.com/torvalds/linux/blob/master/Documentation/trace/coresight/coresight.rst) указывает, что при sysfs usage framework включает промежуточные links после выбора sink и source.

Для `perf` существует штатный выбор sink через `cs_etm/@sink/`, но dummy EUD sink не является обычным memory-backed TMC sink. Поэтому нельзя без проверки заменить `tmc_etr0` на `dummy_sink0` в стандартном `perf record` и ожидать обычный `perf.data`.

### 8.13. OpenCSD

[OpenCSD](https://github.com/Linaro/OpenCSD) — открытая библиотека декодирования ARM CoreSight streams. Исследованный README сообщает версию 1.8.4 и поддержку:

- ETE;
- ETMv4;
- PTM;
- ETMv3;
- STM;
- ITM;
- frame deformatting;
- packet processing;
- packet decode;
- интеграцию с `perf`.

OpenCSD описывает обработку в три стадии:

1. удаление CoreSight frame formatting;
2. разделение trace streams на packets;
3. decode packets в program flow.

Прямого EUD input adapter в репозитории не найдено. Для использования после EUD capture необходимо:

- установить фактический формат USB/ATB payload;
- корректно обрабатывать ATID и границы transfers;
- разделить streams при наличии нескольких источников;
- предоставить ETM configuration и Trace IDs;
- для instruction decode предоставить ELF/`vmlinux` и memory images;
- подключить поток к соответствующему decoder API.

**Классификация:** потенциально совместимый decoder, но не готовая поддержка EUD.

### 8.14. QDSS — отдельный trace-over-USB путь

QDSS — Qualcomm Debug Subsystem. В downstream-ядрах найдены реальные реализации:

- [`f_qdss.c`](https://github.com/MotorolaMobilityLLC/kernel-msm/blob/MMI-S1RFS32.27-25-12/drivers/usb/gadget/function/f_qdss.c);
- [`u_qdss.c`](https://github.com/MotorolaMobilityLLC/kernel-msm/blob/MMI-S1RFS32.27-25-12/drivers/usb/gadget/function/u_qdss.c).

`f_qdss.c` создаёт vendor-specific USB interfaces:

- `QDSS DATA`: один bulk IN endpoint;
- опциональный `QDSS CTRL`: bulk IN и bulk OUT;
- High Speed packet size 512;
- SuperSpeed packet size 1024;
- Full Speed descriptors также присутствуют, хотя `qdss_set_alt()` отклоняет full/low speed;
- configfs channel name имеет формат `qdss.<channel_name>`;
- доступны `usb_qdss_open()`, `usb_qdss_close()`, `usb_qdss_write()` и связанная инфраструктура.

`u_qdss.c` соединяет QDSS BAM pipe с USB и использует request размером `32*1024`.

Это реальный target-side QDSS-over-USB transport, но он отделён от EUD TRACE USB PID `0x9502`. Не найдено открытого host tool, который превращал бы этот поток в готовый EUD/OpenCSD workflow.

**Классификация:** рабочий компонент другого Qualcomm trace transport; не доказательство поддержки EUD TRACE.


## 9. COM

### 9.1. Host-side API в `quic/eud`

COM должен появляться как USB-устройство Qualcomm **`05c6:9505`**. В [`inc/device_manager_defines.h`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/inc/device_manager_defines.h) Windows device name при этом жёстко задан как:

```c
#define EUD_COM_DEVMGR_NAME "\\\\.\\COM10"  // FIXME
#define EUD_COM_DEVMGR_BASENAME "COM10"     // FIXME
```

Это не универсальное обнаружение последовательного порта, а незавершённая platform-specific часть.

В [`src/com_api.cpp`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/src/com_api.cpp) описан пакет фиксированного максимального размера:

| Байты | Содержимое |
|---|---|
| `0` | Execution environment ID или UART ID |
| `1` | Длина payload |
| `2…15` | До 14 байт payload |

Базовый идентификатор — `0x80`. В комментариях и коде перечислены execution environments:

| ID | Execution environment |
|---:|---|
| `0x81` | APPS |
| `0x82` | CDSP |
| `0x84` | MPSS |
| `0x85` | ADSP |
| `0x86` | SLPI |
| `0x88` | SP |

В [`inc/com_eud.h`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/inc/com_eud.h) определены команды конфигурации:

```c
#define COM_CMD_NOP         0
#define COM_CMD_TX_TMOUT    1
#define COM_CMD_RX_TMOUT    2
#define COM_CMD_PORT_RESET  3
```

Однако единственный экспортируемый высокоуровневый API фактически является тестом:

```c
EXPORT EUD_ERR_t test_function(uint32_t deviceID, uint8_t ExecEnvID)
```

Он инициализирует COM и задаёт TX/RX timeout, но USB write/read находятся в закомментированном блоке `FIXME`; активный цикл преимущественно выполняет ожидание `usleep()`. Общих функций вида `com_read()` и `com_write()` в публичном API нет.

Issue [`#6 — Will serial/com via EUD be supported in future?`](https://github.com/quic/eud/issues/6) прямо фиксирует пользовательский вопрос о незавершённости COM API. На момент исследования содержательного официального ответа с готовой реализацией там не было.

**Вывод по host-side:** формат команд и транспортная основа известны, но публичный `libeud` не предоставляет завершённый последовательный client.

### 9.2. Target-side reference в ядре Motorola

Наиболее полный открытый reference найден в [`drivers/soc/qcom/eud.c`](https://github.com/MotorolaMobilityLLC/kernel-msm/blob/MMI-S1RFS32.27-25-12/drivers/soc/qcom/eud.c) репозитория `MotorolaMobilityLLC/kernel-msm`, tag `MMI-S1RFS32.27-25-12`.

Для последовательного канала используются:

```c
#define UART_ID       0x90
#define MAX_FIFO_SIZE 14

#define EUD_REG_COM_TX_ID  0x0000
#define EUD_REG_COM_TX_LEN 0x0004
#define EUD_REG_COM_TX_DAT 0x0008
#define EUD_REG_COM_RX_ID  0x000C
#define EUD_REG_COM_RX_LEN 0x0010
#define EUD_REG_COM_RX_DAT 0x0014
```

Драйвер реализует:

- RX и TX interrupts;
- `uart_ops`;
- приём в `eud_uart_rx()`;
- передачу в `eud_uart_tx()`;
- регистрацию UART с `.dev_name = "ttyEUD"`.

При обычной нумерации первого порта на target появляется **`/dev/ttyEUD0`**. Комментарии `libeud` описывают соответствующую последовательность записей `COM_TX_ID`, `COM_TX_LEN`, `COM_TX_DAT` и чтения RX registers, поэтому host packet format и target register interface согласуются.

**Классификация:** рабочий target-side компонент в OEM/downstream-коде. Его наличие не означает, что со стороны host уже есть открытая программа для обмена данными.

### 9.3. Публичные признаки регистрации `ttyEUD`

Строка `ttyEUD0 ... is a EUD UART` встречается в журналах разных Qualcomm/Android и embedded-платформ:

- [QSDK IPQ5018 на TP-Link](https://gist.github.com/ptpt52/ae47eb7b86ce2911df06d067152f02ac): `58000.qcom,msm-eud: ttyEUD0 ... is a EUD UART`;
- [Moto G50](https://robbins.page/posts/attempting-qualcomm-eud-moto-g50/): регистрация `ttyEUD0` после ошибки secure write;
- [RedMagic 6 device database](https://newandroidbook.com/ddb/RedMagic6/): в списке устройств присутствует `ttyEUD0`;
- [OpenWrt/Snapdragon X72](https://forum.openwrt.org/t/dw5934e-snapdragon-x72-4g-5g-modem/244169): `ttyEUD0` виден среди device nodes.

Эти наблюдения подтверждают, что downstream-драйвер реально развёртывался на разных устройствах. Но регистрация tty — не доказательство успешного host↔target обмена: для этого нужны включённый EUD COM peripheral, появление `05c6:9505`, host client и фактический RX/TX test.

### 9.4. Отрицательный практический тест на Moto G50

В публикации [Exploring Qualcomm EUD on Moto G50](https://robbins.page/posts/attempting-qualcomm-eud-moto-g50/) Device Tree содержал EUD node, а kernel зарегистрировал UART, но secure enable завершился ошибкой:

```text
msm-eud 1628000.qcom,msm-eud: TCSR qcom_scm_io_writel failed with rc:-22
1628000.qcom,msm-eud: ttyEUD0 ... is a EUD UART
```

Попытка прямой записи:

```sh
devmem 0x16281014 4 1
```

привела к watchdog reset. Автор не смог включить EUD на этом устройстве. Это важный контрпример: наличие DT node и `ttyEUD0` не гарантирует доступность debug hardware, а прямые register writes на защищённой платформе могут быть небезопасны.

### 9.5. Минимальный план самостоятельного host client

На основе открытого packet format и Motorola target reference наименьший проверяемый проект выглядит так:

1. Через CTRL включить COM peripheral и убедиться в USB enumeration `05c6:9505`.
2. Открыть COM function через `libusb`, используя endpoint discovery, а не предполагая Windows `COM10`.
3. Отправить команды `COM_CMD_TX_TMOUT` и `COM_CMD_RX_TMOUT`.
4. Для канала target UART использовать ID `0x90`.
5. Передавать пакеты `[0x90, length, payload…]`, где `length ≤ 14`.
6. На приёме проверять ID и length, собирать payload из нескольких пакетов и обрабатывать partial/zero-length USB reads.
7. На target читать и писать `/dev/ttyEUD0`; сначала выполнить короткий loop/echo test, затем duplex test.
8. Реализовать error recovery, port reset и корректное закрытие USB.

До аппаратной проверки это **обоснованный план реализации**, а не готовая команда. Необходимо отдельно подтвердить USB endpoints и точную packing-семантику на выбранном SoC.

**Итог COM:** target-side реализация существует; открытый host-side API остаётся экспериментальной заглушкой. Из трёх незавершённых функций COM выглядит наиболее компактной задачей для самостоятельного client.

## 10. JTAG

### 10.1. Низкоуровневый API `quic/eud`

В [`src/jtag_api.cpp`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/src/jtag_api.cpp) и [`inc/jtag_api.h`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/inc/jtag_api.h) присутствуют:

```c
jtag_peripheral_reset()
jtag_flush()
jtag_set_delay()
jtag_bitbang()
jtag_tms()
jtag_nbit_toss()
jtag_nbit_keep()
jtag_nbit_end_toss()
jtag_nbit_end_keep()
jtag_32bit_toss()
jtag_32bit_keep()
jtag_32bit_end_toss()
jtag_32bit_end_keep()
jtag_set_frequency()
jtag_read_frequency()
eud_shift_tdi()
eud_shift_tms()
eud_read_tdo()
```

Это конкретные низкоуровневые операции для управления TAP, TMS/TDI/TDO, bitbang, n-bit/32-bit scan и чтения результата. Они полезны как protocol reference, но не образуют автоматически поддержку JTAG в отладчике.

В [`src/ctl_api.cpp`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/src/ctl_api.cpp) полная exported JTAG initialization отключена:

```cpp
#if 0  // TBD
EXPORT JtagEudDevice* eud_initialize_device_jtag(...)
{
    /* ... */
}
#endif
```

Таким образом, общая CTRL initialization может содержать JTAG enable bits, но нормальный public initialization path для JTAG device не завершён.

### 10.2. Тестовый код не входит в обычную сборку

[`src/jtag_test.cpp`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/src/jtag_test.cpp) содержит TMS/TDI sequences, IR/DR operations и попытку чтения IDCODE. При этом:

- многие последовательности закомментированы;
- в non-FPGA branch часть вызовов доступна только при `EUD_WIN_ENV`;
- файл не доказывает успешный scan chain на реальном устройстве;
- в [`Makefile.am`](https://github.com/quic/eud/blob/693741a3b0448690402539ed0e6af067510e386f/Makefile.am) строка сборки отключена:

```make
#	src/jtag_test.cpp
```

**Классификация:** экспериментальный low-level код и отключённый test, не готовый JTAG debugger.

### 10.3. `linux-msm/openocd`: эксперимент явно помечен `broken`

В [`linux-msm/openocd`](https://github.com/linux-msm/openocd), ветка `eud-rebased`, исследованный commit:

```text
880c11c56b5bc5e8acd2adef5c97ab37b3ca9349
2025-04-01
EUD: try JTAG (broken)
```

[Коммит `880c11c56b5b`](https://github.com/linux-msm/openocd/commit/880c11c56b5bc5e8acd2adef5c97ab37b3ca9349) добавляет `jtag` в список transports наряду со `swd`, но само сообщение прямо называет попытку broken. Это ценный отправной код, а не подтверждённая поддержка.

Инструкция сборки этого дерева для EUD-работ:

```sh
git clone https://github.com/linux-msm/openocd
cd openocd
git submodule update --init
./bootstrap
./configure --enable-eud --disable-linuxgpiod
make -j$(nproc --all)
```

Она относится к экспериментальному дереву. Для воспроизводимого JTAG-исследования следует дополнительно зафиксировать ветку/commit, поскольку HEAD со временем меняется.

### 10.4. Почему другие OpenOCD-реализации не закрывают JTAG

- **Upstream OpenOCD:** [`eud_adapter_driver`](https://github.com/openocd-org/openocd/blob/master/src/jtag/drivers/eud.c) регистрирует `TRANSPORT_SWD`; config называется `eud-swd.cfg`. JTAG-to-SWD sequence лишь переводит DAP в SWD mode.
- **CodeLinaro `qcom_changes`:** [`eud.c`](https://git.codelinaro.org/clo/la/openocd-org/openocd/-/blob/532b9af9e3bde361add988273a9599c53d3cfd8a/src/jtag/drivers/eud.c) содержит `static const char *const eud_transports[] = {"swd", NULL};`; trace callbacks равны `NULL`.
- **Историческая QUTS-интеграция:** в старом коде встречались `QUTS_GATEWAY` и JTAG function pointers, включая `fEUDInitializeDeviceJTG`, но transport оставался SWD-only. Function pointer сам по себе не является работающей JTAG chain.

Commit CodeLinaro [`4c1318349534`](https://git.codelinaro.org/clo/la/openocd-org/openocd/-/commit/4c131834953456e2e4c30c4f262e6ed851579123) от 10 февраля 2025 года сообщает:

```text
Removed QUTS library code for EUD Service
Updated hexagon support
Added EUD submodule
```

Старый README требовал закрытые компоненты QUTS `1.64.1.39` или новее, Qualcomm Host USB Product Suite — QUD QC `1.00.63` и EUD QC `2.1.1`. Это подтверждает существование исторической закрытой integration path, но не даёт открытого воспроизводимого JTAG solution.

### 10.5. Что нужно для завершения открытого JTAG-сценария

Минимальный объём работ:

1. Включить JTAG peripheral через CTRL и открыть `05c6:9503`.
2. Завершить public initialization, frequency/delay configuration и reset handling.
3. Реализовать TAP state machine, TLR, Run-Test/Idle и корректные TMS transitions.
4. Выполнить chain scan, прочитать IDCODE и определить IR lengths всех TAP.
5. Сопоставить low-level `nbit`/`32bit` operations с OpenOCD bitq/scan interface.
6. Обработать USB batching, returned TDO, timeouts, partial transfers и error recovery.
7. Только после устойчивого scan chain подключать DAP/IR/DR operations и target examination.
8. Опубликовать аппаратный log: enumeration, IDCODE, chain layout, DAP discovery и повторяемый debug session.

Пока такого подтверждённого открытого log не найдено.

**Итог JTAG:** есть самый полезный набор низкоуровневых команд и broken-эксперимент, но это наиболее объёмная из рассмотренных задач доработки. Готового открытого JTAG-over-EUD end-to-end solution не обнаружено.


## 11. Сводная матрица связанных проектов

| Проект / источник | Что реально найдено | CTRL | SWD | JTAG | TRACE | COM |
|---|---|---:|---:|---:|---:|---:|
| [`quic/eud`, `main`](https://github.com/quic/eud) | Базовая `libeud`, USB scanner и peripheral APIs | Рабочие API | Низкоуровневая реализация | Low-level, init `#if 0`, test не собирается | Незавершённый capture | Stub/`FIXME` |
| [`quic/eud`, `EUD_Trace_Support`](https://github.com/quic/eud/tree/EUD_Trace_Support) | Четыре новых TRACE-коммита, caller-buffer API, test client | Наследуется | Наследуется | Не завершён | **Активная незавершённая ветка** | Не завершён |
| [`quic/eud`, `File_Logging_Support`](https://github.com/quic/eud/tree/File_Logging_Support) | TRACE-ветка плюс file logging | Наследуется | Наследуется | Нет новой реализации | Capture + logging | Нет новой реализации |
| [Upstream OpenOCD](https://github.com/openocd-org/openocd/blob/master/src/jtag/drivers/eud.c) | Самостоятельный `libusb` EUD adapter | Enable SWD | **Подтверждённый transport** | Нет | Callbacks не образуют EUD trace workflow | Нет |
| [`linux-msm/openocd`](https://github.com/linux-msm/openocd) | Экспериментальная работа и practical quickstart | Есть | Рабочая основа | **Commit `try JTAG (broken)`** | Нет готовой интеграции | Нет |
| [CodeLinaro OpenOCD `qcom_changes`](https://git.codelinaro.org/clo/la/openocd-org/openocd) | Qualcomm platform configs, ADIv6 handling, standalone trace test | Есть | SWD-only | Нет готового transport | Отдельный `test_trace.c`, не OpenOCD callbacks | Нет |
| [Linux `qcom_eud.c`](https://github.com/torvalds/linux/blob/master/drivers/usb/misc/qcom_eud.c) | Target/platform enable, SCM, USB role switch | **Platform enable path** | Необходимая основа | Не доказывает JTAG | Не захватывает trace | Не реализует host COM |
| [Linux CoreSight dummy](https://github.com/torvalds/linux/blob/master/drivers/hwtracing/coresight/coresight-dummy.c) | EUD как externally controlled CoreSight sink | Не относится | Не относится | Не относится | **Topology/path component** | Не относится |
| [Motorola `drivers/soc/qcom/eud.c`](https://github.com/MotorolaMobilityLLC/kernel-msm/blob/MMI-S1RFS32.27-25-12/drivers/soc/qcom/eud.c) | Полный target-side EUD UART | Target enable | Нет host debugger | Нет | Нет USB host decode | **RX/TX, IRQ, `ttyEUD`** |
| [OpenCSD](https://github.com/Linaro/OpenCSD) | CoreSight frame/packet/instruction decoders | Нет | Нет | Нет | **Потенциальный decoder после адаптера** | Нет |
| [Motorola QDSS gadget](https://github.com/MotorolaMobilityLLC/kernel-msm/blob/MMI-S1RFS32.27-25-12/drivers/usb/gadget/function/f_qdss.c) | Отдельный QDSS-over-USB transport | Нет | Нет | Нет | Другой transport, не `05c6:9502` | Нет |
| QUTS / исторический CodeLinaro | Закрытые зависимости, EUD Service, отдельные function pointers | Закрытая integration path | Использовался SWD | Упоминания без открытой chain | Упоминание и test API | Нет открытого client |
| Lauterbach TRACE32 | Общие Qualcomm JTAG/CoreSight и Hexagon workflows | Не установлено | Не установлено | Нет доказательства использования открытого `05c6:9503` | Нет доказательства использования открытого `05c6:9502` | Не установлено |

Важное следствие матрицы: **CoreSight topology, USB capture и packet decode — три разных компонента TRACE**, а target UART и host COM client — два разных компонента COM. Наличие одного не следует засчитывать как готовность всего сценария.

## 12. Проверенные форки `quic/eud`

Были проверены основные ветки и публично видимые изменения следующих форков:

- [`yeshuibo/eud`](https://github.com/yeshuibo/eud);
- [`strongtz/eud`](https://github.com/strongtz/eud);
- [`015stray91/eud`](https://github.com/015stray91/eud);
- [`aashiqa786/eud`](https://github.com/aashiqa786/eud);
- [`arturkow2000/eud`](https://github.com/arturkow2000/eud);
- [`gavz/eud`](https://github.com/gavz/eud);
- [`kcxt/eud`](https://github.com/kcxt/eud);
- [`CrackerCat/eud`](https://github.com/CrackerCat/eud);
- [`quic-kdybcio/eud`](https://github.com/quic-kdybcio/eud);
- [`junyang0412/eud`](https://github.com/junyang0412/eud).

В их основных публичных ветках не найдено завершённых улучшений TRACE, COM или JTAG, которые меняли бы итоговую классификацию. Наиболее содержательная работа обнаружена не в стороннем форке, а в официальных feature branches `EUD_Trace_Support` и `File_Logging_Support`.

В [pull requests `quic/eud`](https://github.com/quic/eud/pulls) встречались Meson/build fixes, warnings и dependabot changes. Завершающего COM/JTAG pull request не обнаружено. Это наблюдение относится к проверенному состоянию репозитория на дату исследования и не исключает последующих изменений.

## 13. История и состояние основного репозитория

Исследованный `main` `quic/eud` зафиксирован на:

```text
693741a3b0448690402539ed0e6af067510e386f
```

Наиболее значимые для исследования изменения:

| Commit | Дата | Значение |
|---|---|---|
| [`392ce5d3e940`](https://github.com/quic/eud/commit/392ce5d3e940) | 31 июля 2025 | Support for ADIV6, EUD Trace and updates in CTL and SWD Peripheral |
| [`ed4f15980e74`](https://github.com/quic/eud/commit/ed4f15980e74) | 22 октября 2025 | Merge PR `#2` с OpenOCD fixes |
| [`213af7d157b7`](https://github.com/quic/eud/commit/213af7d157b7) | 23 октября 2025 | Merge pull request `#5` |
| [`693741a3b044`](https://github.com/quic/eud/commit/693741a3b0448690402539ed0e6af067510e386f) | 1 апреля 2026 | Adding `.github` folder |

Для TRACE критично смотреть не только на `main`: feature branch содержит более новый API и исправления, которых нет в исследованном основном HEAD.

### 13.1. Сборка `libeud`

README предлагает:

```sh
autoreconf --verbose --force --install
./configure
make
```

На Linux необходим development package **`libusb-1.0-0-dev`**. Проверочная сборка остановилась на:

```text
fatal error: libusb-1.0/libusb.h: No such file or directory
```

Это ошибка отсутствующей build dependency, а не доказательство неисправности исходников. После установки зависимости сборку нужно повторять отдельно; аппаратная работоспособность периферий всё равно проверяется независимо.

## 14. Внешние закрытые и коммерческие инструменты

### 14.1. QUTS

QUTS упоминается в двух разных контекстах:

1. Старый CodeLinaro OpenOCD использовал закрытый QUTS/EUD Service и Qualcomm USB packages.
2. Commit `3392e3a5ec52` в `EUD_Trace_Support` готовит TRACE API для third-party tools «like QUTs».

Публичные исходники при этом не раскрывают полный закрытый QUTS workflow. Поэтому корректно считать QUTS историческим или потенциальным потребителем API, но не ссылаться на него как на открытую реализацию JTAG/TRACE/COM.

### 14.2. Lauterbach TRACE32

Для TRACE32 доступны общие сведения о Qualcomm JTAG debugging, CoreSight trace и Hexagon support. Однако в проверенных материалах не найдено доказательств, что конкретный открытый USB interface EUD JTAG `05c6:9503` или TRACE `05c6:9502` используется готовым TRACE32 driver.

Следовательно, общий Qualcomm/CoreSight workflow TRACE32 нельзя автоматически причислять к реализациям EUD. Для такого утверждения потребовалась бы документация на конкретный adapter/interface или подтверждённый hardware log с этими PID.

## 15. Практические рекомендации

### 15.1. Если нужна отладка прямо сейчас — использовать SWD

Наиболее короткий открытый путь:

1. Проверить SoC, DT, secure EUD и USB role-switch support.
2. Включить EUD platform driver или выполнить SoC-specific enable.
3. Использовать основной OpenOCD с `adapter driver eud` и `transport select swd`.
4. Проверить DPIDR, DAP discovery, CPU examination, halt/resume и GDB server.
5. Не путать успешный SWD с доступностью JTAG, TRACE или COM — каждая периферия требует отдельной проверки.

Это единственный сценарий, для которого найден полный публичный журнал от USB/EUD до отладки CPU.

### 15.2. COM — наименьший самостоятельный проект

При наличии устройства, где CTRL успешно включает COM и target экспортирует `/dev/ttyEUD0`, начать с небольшого `libusb` client:

- реализовать packet framing с ID `0x90` и 14-byte chunks;
- добавить TX/RX timeout и port reset;
- сделать очередь TX и reassembly RX;
- проверить однобайтный, 14-byte, 15-byte и длинный transfer;
- проверить одновременный RX/TX и reconnect.

Готовый Motorola target driver существенно снижает неопределённость протокола. Основной риск — не framing, а platform security и фактическое включение USB COM peripheral.

### 15.3. TRACE — перспективно, но нужна цепочка из нескольких компонентов

Рекомендуемый порядок:

1. **Зафиксировать target topology:** источник ETM/ETE/STM, Trace ID, funnel/replicator/ETF и `dummy-eud` sink.
2. **Проверить target-side activation:** сначала независимо от host decoder убедиться, что CoreSight path включается и EUD TRACE enumerates как `05c6:9502`.
3. **Взять за основу `EUD_Trace_Support`, а не старый `main`:** новый caller-buffer API удобнее для внешнего client.
4. **Исправить capture edge cases:** zero-length successful reads, timeout с partial data, сохранение излишка из guard buffer, shutdown и reconnect.
5. **Определить wire format:** сохранять одновременно полностью сырой USB stream и обработанный stream; не удалять ATID/length до подтверждения их семантики.
6. **Написать ATB/ATID parser:** отделять framing и streams разных источников.
7. **Подключить OpenCSD:** предоставить decoder configuration, Trace IDs, ELF/`vmlinux` и memory images для instruction decode.
8. **Проверять по известной нагрузке:** сгенерировать простой известный instruction flow или STM events и сравнить decoded output с ожидаемым.

До выполнения этих шагов `Trace.bin` следует называть **сырым или частично обработанным capture**, а не декодированным CoreSight trace.

### 15.4. JTAG — сначала scan chain, затем интеграция с отладчиком

Не начинать с CPU examination. Первый критерий успеха — стабильный TAP reset и повторяемый IDCODE/chain scan. Затем нужно реализовать OpenOCD scan/bitq interface и error recovery. Только после этого имеет смысл подключать DAP и target configs.

### 15.5. Безопасность и воспроизводимость аппаратных тестов

- Не переносить register addresses из SDM845, Moto G50 или другого SoC без проверки документации и DT выбранного устройства.
- Не обходить secure debug policy прямыми записями: Moto G50 показывает возможность watchdog reset.
- Перед тестом сохранять `dmesg`, `lsusb`, DT nodes и версии kernel/OpenOCD/libeud.
- Для отрицательного результата различать: нет USB enumeration, SCM denial, USB role-switch problem, protocol error и decoder error.
- Для положительного результата публиковать не только screenshot USB device, но и функциональный log: SWD DPIDR/CPU halt, COM RX/TX, JTAG IDCODE/chain, TRACE raw stream/decode.

## 16. Окончательный вывод

Открытая экосистема Qualcomm EUD неоднородна:

- **CTRL** имеет конкретные рабочие реализации и является общей точкой включения, но зависит от secure/platform state.
- **SWD** полностью подтверждён: основной OpenOCD содержит прямой EUD adapter, а Linaro опубликовала DAP/CPU/GDB log на Snapdragon 845.
- **JTAG** остаётся экспериментальным: low-level API и test sequences есть, public initialization отключён, test не собирается по умолчанию, а попытка в `linux-msm/openocd` помечена `broken`.
- **TRACE** получил заметную работу в 2026 году: отдельная ветка предоставляет новый capture API и test client. Но zero-length/timeout/guard-buffer cases, формат ATID/ATB, target CoreSight configuration и OpenCSD integration требуют доработки и аппаратной проверки.
- **COM** имеет сильный target-side reference с `ttyEUD`, RX/TX и известным packet format, однако host-side публичный `libeud` API остаётся незавершённым.

Таким образом, заявленные пять функций отражают возможности аппаратного блока и архитектуру интерфейсов, а не пять готовых открытых пользовательских инструментов. Для практической работы сегодня наиболее обоснованы: **SWD — готовое использование; COM — небольшой самостоятельный client; TRACE — интеграционный проект средней сложности; JTAG — наиболее объёмная доработка.**

## 17. Основные первоисточники

Ниже собран компактный реестр ключевых источников; более конкретные commit, branch, file и practical-test links приведены непосредственно в соответствующих разделах.

1. [Qualcomm `quic/eud`](https://github.com/quic/eud) — основная открытая библиотека.
2. [`EUD_Trace_Support`](https://github.com/quic/eud/tree/EUD_Trace_Support) — новая TRACE-работа.
3. [`File_Logging_Support`](https://github.com/quic/eud/tree/File_Logging_Support) — file logging поверх TRACE-ветки.
4. [Upstream OpenOCD EUD driver](https://github.com/openocd-org/openocd/blob/master/src/jtag/drivers/eud.c) — прямой SWD-over-EUD adapter.
5. [OpenOCD Gerrit change 9773](https://review.openocd.org/c/openocd/+/9773) — история upstream merge.
6. [`linux-msm/openocd`](https://github.com/linux-msm/openocd) — экспериментальная разработка и quickstart.
7. [Qualcomm CodeLinaro OpenOCD](https://git.codelinaro.org/clo/la/openocd-org/openocd) — Qualcomm downstream integration.
8. [Linaro: The hidden JTAG in your Qualcomm/Snapdragon device’s USB port](https://www.linaro.org/blog/hidden-jtag-qualcomm-snapdragon-usb/) — практическое введение и подтверждённый SWD log.
9. [Linux `qcom_eud.c`](https://github.com/torvalds/linux/blob/master/drivers/usb/misc/qcom_eud.c) — platform enable и USB role switch.
10. [Linux CoreSight dummy sink binding](https://github.com/torvalds/linux/blob/master/Documentation/devicetree/bindings/arm/arm,coresight-dummy-sink.yaml) — EUD как externally controlled sink.
11. [Linux CoreSight dummy driver](https://github.com/torvalds/linux/blob/master/drivers/hwtracing/coresight/coresight-dummy.c) — topology component.
12. [OpenCSD](https://github.com/Linaro/OpenCSD) — CoreSight decode library.
13. [Motorola EUD kernel driver](https://github.com/MotorolaMobilityLLC/kernel-msm/blob/MMI-S1RFS32.27-25-12/drivers/soc/qcom/eud.c) — target-side COM/UART reference.
14. [Moto G50 practical attempt](https://robbins.page/posts/attempting-qualcomm-eud-moto-g50/) — DT, secure enable failure и watchdog reset.
15. [Motorola QDSS USB function](https://github.com/MotorolaMobilityLLC/kernel-msm/blob/MMI-S1RFS32.27-25-12/drivers/usb/gadget/function/f_qdss.c) и [BAM/USB glue](https://github.com/MotorolaMobilityLLC/kernel-msm/blob/MMI-S1RFS32.27-25-12/drivers/usb/gadget/function/u_qdss.c) — отдельный QDSS-over-USB transport.
