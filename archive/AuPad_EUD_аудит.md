# Аудит реализации Qualcomm EUD в aupad-linux

**Дата:** 11 ноября 2026 года  
**Проверенная revision:** [`72875cb9aef1021f9466c5bdf0abff3d9ff1a17c`](https://github.com/sleeply4cat/aupad-linux/tree/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c)  
**Платформа:** CHUWI AuPad, Snapdragon 680 / SM6225 / khaje  
**Предмет:** архитектурные допущения, отклонения от принятых практик и улучшения реализаций EUD COM и SWD.

## 1. Резюме

Репозиторий содержит содержательную end-to-end реализацию отладки через Qualcomm EUD: stub включает EUD, Linux и U-Boot реализуют двунаправленный COM console, host logger поддерживает ввод и вывод, а OpenOCD получает практические исправления для SWD на SM6225.

Для задач bring-up выбранные решения в основном обоснованы. При этом код пока не следует считать универсальным драйвером Qualcomm EUD или готовым upstream patch set без дополнительной работы. Главные проблемы относятся не к базовым register sequences, а к следующим областям:

1. handover между `earlycon` и полноценной `ttyEUD0`;
2. PHY lifecycle при последующем выключении EUD;
3. неограниченное ожидание ACK TX-ready в stub;
4. восстановление host logger после USB-ошибок;
5. проверка COM framing и ACK;
6. обработка ошибок libusb и AArch64 mode switching в OpenOCD;
7. включение debug peripheral по умолчанию в общем SM6225 DTSI;
8. недостаточно формализованный project-specific ACK/hello protocol.

Наиболее важные исправления для текущего AuPad workflow: не сочетать `keep_bootcon` с полноценной `ttyEUD0`, ограничить ожидание в stub и исправить reconnect/error paths в `eudlog.py`. Для универсального или upstream варианта дополнительно необходимо исправить PHY state machine и Device Tree integration.

## 2. Область аудита и границы выводов

Рассмотрены:

- host client [`tools/eudlog.py`](https://github.com/sleeply4cat/aupad-linux/blob/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/tools/eudlog.py);
- EUD handshake в [`stub/main.c`](https://github.com/sleeply4cat/aupad-linux/blob/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/stub/main.c#L381-L421);
- Linux earlycon [`0027-tty-serial-add-a-boot-console-over-Qualcomm-EUD-COM.patch`](https://github.com/sleeply4cat/aupad-linux/blob/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/patches/linux/0027-tty-serial-add-a-boot-console-over-Qualcomm-EUD-COM.patch);
- Linux PHY handover [`0029-phy-qcom-snps-femto-v2-leave-the-PHY-alone-while-EUD.patch`](https://github.com/sleeply4cat/aupad-linux/blob/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/patches/linux/0029-phy-qcom-snps-femto-v2-leave-the-PHY-alone-while-EUD.patch);
- Linux serial port и console [`0031-tty-serial-add-a-serial-port-and-console-over-Qualco.patch`](https://github.com/sleeply4cat/aupad-linux/blob/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/patches/linux/0031-tty-serial-add-a-serial-port-and-console-over-Qualco.patch);
- Device Tree binding и SM6225 DTS в patches `0030` и [`0032`](https://github.com/sleeply4cat/aupad-linux/blob/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/patches/linux/0032-arm64-dts-qcom-sm6225-describe-EUD-COM-and-the-PHY-s.patch);
- U-Boot PHY, DWC3 handover и [`serial_qcom_eud.c`](https://github.com/sleeply4cat/aupad-linux/blob/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/patches/u-boot/0008-serial-add-a-console-over-Qualcomm-EUD-COM.patch);
- OpenOCD [`eud-sm6225.patch`](https://github.com/sleeply4cat/aupad-linux/blob/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/tools/ocd/eud-sm6225.patch) и `khaje.cfg`.

Независимые проверки, выполненные до этого аудита:

- patch OpenOCD применён к указанной базе, patched OpenOCD успешно собран;
- полная серия U-Boot patches последовательно применена;
- COM host protocol частично проверен mock-тестами;
- полная сборка Linux tree не выполнена;
- испытания на физическом AuPad независимо не повторялись.

Поэтому аппаратные показатели из `docs/PORT.md` — 10 000 строк earlycon без ошибок, 0 ошибок на 200 000 non-posted пакетов, 12/12 GDB reconnects, скорость COM и диапазон рабочих SWD frequencies — являются **результатами автора**, а не независимо воспроизведёнными результатами данного аудита.

JTAG transport и EUD TRACE в репозитории не реализованы. Наличие соответствующих USB PID в документации не подтверждает поддержку этих функций кодом.

## 3. Классификация основных находок

| ID | Компонент | Класс | Важность | Краткое содержание |
|---|---|---|---|---|
| D1 | Linux earlycon/full console | Подтверждённый дефект конфигурации | Высокая при совместном использовании | `keep_bootcon` оставляет два console writer на одном COM |
| D2 | Linux PHY | Подтверждённый lifecycle-дефект | Высокая для generic, латентная для фиксированного AuPad | После EUD on → off повторный init может не настроить PHY |
| D3 | Stub | Подтверждённый дефект | Средняя/высокая | Неограниченный ACK wait и отсутствие проверки hello |
| D4 | `eudlog.py` | Подтверждённый дефект | Средняя | Постоянная USB-ошибка может удержать процесс в `resync()` |
| D5 | COM host/target | Подтверждённый дефект robustness | Средняя | Не проверяются length, record boundary и ACK payload |
| D6 | OpenOCD | Подтверждённый пробел error handling | Средняя | Игнорируются ошибки configuration, halt cleanup и mode restoration |
| I1 | SM6225 DTSI | Отклонение от DTS integration practice | Средняя | Debug node enabled для всех SM6225 boards |
| I2 | SM6225 DTSI | Спорное/неподтверждённое описание IRQ | Низкая/средняя | SPI 189 описан, но драйвер его не использует, а доставка не подтверждена |
| I3 | COM protocol | Ограничение переносимости | Средняя для upstream | AuPad ACK/hello не доказан как общий Qualcomm COM protocol |
| A1 | MMIO и polling | Обоснованное platform-specific допущение | Не дефект | Non-posted mapping и polling выбраны по аппаратным измерениям |
| A2 | OpenOCD timings | Platform-specific workaround | Не дефект для khaje | 7,5 MHz, gaps и enable cycling нельзя автоматически распространять на все EUD |
| S1 | Root getty | Осознанный debug-режим | Высокая для production | Неаутентифицированный root shell не должен попадать в production image |

## 4. Подтверждённые дефекты и необходимые исправления

### 4.1. D1 — handover `earlycon` в `ttyEUD0`

Linux earlycon реализован через отдельный `early_console_dev.port`, а полноценная console — через `eud_com_console_port` и собственный UART port lock. Оба пути обращаются к одному EUD COM TX FIFO.

Согласно [документации Linux console](https://docs.kernel.org/driver-api/tty/console.html), console с `CON_BOOT` автоматически отключается при появлении полноценной console, если не указан `keep_bootcon`. Следовательно, сочетание:

```text
earlycon=qcom_eud,0x1610000 console=ttyEUD0 keep_bootcon
```

оставляет оба writer активными. Возможные последствия:

- повторная отправка printk messages;
- независимый MMIO-доступ к одному hardware FIFO;
- race между оставшимся earlycon и UART RX/TX polling, поскольку их port locks не общие.

`CON_PRINTBUFFER` предотвращает повтор старого backlog при регистрации полноценной console, но не устраняет продолжающийся параллельный вывод при `keep_bootcon`.

**Рекомендуемые режимы:**

```text
# Только ранняя и постоянная boot console
earlycon=qcom_eud,0x1610000 keep_bootcon

# Стандартный handover в полноценную console
earlycon=qcom_eud,0x1610000 console=ttyEUD0
```

Во втором режиме `keep_bootcon` следует убрать. Документацию и boot scripts нужно изменить так, чтобы два режима не смешивались.

### 4.2. D2 — PHY lifecycle после EUD on → off

Patch PHY добавляет ранний возврат из `qcom_snps_hsphy_init()` при `phy_initialized`, а `qcom_snps_hsphy_exit()` при включённом EUD сохраняет clocks/regulators и не сбрасывает этот флаг.

Из кода следует такая последовательность:

1. `phy_init()` при EUD on включает resources, но пропускает reset и обычную programming sequence;
2. `phy_exit()` при EUD on сохраняет resources и `phy_initialized = true`;
3. EUD выключается;
4. следующий `phy_init()` возвращается по `phy_initialized`;
5. обычная настройка PHY остаётся невыполненной.

Это не мешает сценарию AuPad с постоянно включённым EUD, но является дефектом для динамического enable/disable и обобщённого драйвера.

**Исправление:** не использовать один флаг для разных состояний. Минимально полезно разделить:

- `powered` — clocks/regulators включены или сознательно сохранены;
- `programmed` — обычная PHY programming sequence выполнена;
- `eud_preserved` — resources сохранены для EUD.

При повторном `phy_init()` с сохранёнными resources, выключенным EUD и `programmed == false` необходимо выполнить обычную настройку без повторного включения resources.

Runtime suspend также не должен изменять PHY registers, пока EUD владеет линией. В проверенной mainline версии runtime PM по умолчанию запрещён через `pm_runtime_forbid()`, а callback в host mode может изменять PHY registers. Поэтому это требование для общего драйвера и явно включённого runtime PM, а не доказанный текущий сбой AuPad.

### 4.3. D3 — hello handshake и ACK wait в stub

После получения RX packet stub выполняет:

```c
while (!(rd(0x01610044) & 2))
	;
```

Ожидание hello ограничено `STUB_EUD`, но это ожидание TX-ready уже не ограничено. Если host исчез после отправки hello, stub может зависнуть после исчерпания предполагаемого handshake timeout.

Дополнительно stub не читает RX ID и не проверяет, что получен именно hello `[ID=0x91, length=1, payload=0x05]`. Любой входящий пакет завершает ожидание.

**Исправление:**

1. прочитать RX ID и length;
2. полностью дренировать пакет, чтобы освободить hardware RX;
3. принять его как hello только при `id == 0x91 && len == 1 && payload == 0x05`;
4. остальные пакеты подтверждать, но продолжать ожидание;
5. ограничить ACK TX-ready wait через `read_cntpct()` deadline;
6. при timeout не блокировать дальнейшую загрузку бесконечно.

### 4.4. D4 — reconnect и recovery в `eudlog.py`

`Tx.resync()` после не-timeout `USBError` бесконечно повторяет clear halt и NOP. При отключении устройства постоянная `NoDeviceError` или аналогичная ошибка может не попасть во внешний reconnect loop.

Таким образом, заявленное следование за перезагрузками зависит от места возникновения ошибки: ошибка в основном read path обрабатывается внешним циклом, а постоянная ошибка внутри TX recovery может заблокировать этот цикл.

**Исправление:**

- ограничить recovery небольшим числом попыток;
- disconnect/no-device ошибки сразу пробрасывать наружу;
- после неудачного recovery освобождать USB resources;
- возвращаться в общий discovery/reconnect loop;
- покрыть сценарии disconnect во время read, write, clear halt и NOP.

### 4.5. D5 — проверка COM framing

COM packet имеет вид `[ID, length, up to 14 payload bytes]`. В текущем host parser недостаточно проверок:

- `length <= 14`;
- наличие всех `2 + length` байтов в соответствующей record;
- ACK `length == 1`;
- ACK payload `0x06`.

При malformed length host slicing может включить padding или байты следующей record. Любой входящий ID `0x91` освобождает ожидающий TX, даже если это не корректный ACK.

Linux и U-Boot полностью дренируют указанную length, что правильно для освобождения pending packet, но не ограничивают её protocol constant. В U-Boot переполнение RX buffer предотвращено проверкой `rx_len < EUD_COM_PACKET_MAX`; в Linux per-character insert также не приводит к переполнению собственного packet buffer. Проблема заключается в приёме malformed stream и лишних MMIO reads, а не в доказанном memory corruption.

**Минимальная host validation:**

```text
header доступен полностью
length <= 14
record_start + 2 + length <= received_size
data packet: ID == 0x90
ACK: ID == 0x91 && length == 1 && payload == 0x06
```

Target должен дренировать malformed packet для восстановления transport, но не передавать его содержимое в TTY как нормальный ввод. Полезно добавить счётчики malformed RX, dropped TX и ACK timeout.

### 4.6. D6 — OpenOCD error propagation и restoration

В patch не проверяются return values:

- `libusb_set_configuration()`;
- `libusb_clear_halt()`;
- `armv8_dpm_modeswitch()` при EL0 → EL1;
- обратного mode switch;
- `dpm->finish()`.

Для новой AArch64 `mrs` команды это особенно важно. Если переход в EL1 не удался, чтение system register может происходить в неправильном режиме. Если не удалось обратное переключение, состояние target context может остаться изменённым.

**Исправление:** использовать единый cleanup path:

1. сохранить первую ошибку операции;
2. всегда попытаться восстановить исходный режим;
3. всегда выполнить требуемый `finish()`;
4. ошибку restoration не скрывать, а диагностировать;
5. для libusb проверять и логировать результат, отдельно обрабатывая допустимые состояния вроде уже установленной configuration или отсутствия halt.

## 5. Device Tree и интеграция с mainline

### 5.1. I1 — debug node enabled по умолчанию

Node `serial@1610000` добавлен в общий `sm6225.dtsi` без `status = "disabled"`. Согласно [DTS Coding Style](https://docs.kernel.org/devicetree/bindings/dts-coding-style.html), отсутствие `status` означает enabled; типичная схема предполагает peripheral disabled в SoC DTSI и включение в board DTS.

Здесь это имеет функциональный эффект: driver probe вызывает `devm_clk_get_optional_enabled()` и может удерживать clock vote на всех SM6225 boards, включая устройства без EUD console.

Рекомендуемая структура:

```dts
/* sm6225.dtsi */
eud_com: serial@1610000 {
	compatible = "qcom,sm6225-eud-com", "qcom,eud-com";
	reg = <0x0 0x01610000 0x0 0x1000>;
	clocks = <&gcc GCC_AHB2PHY_USB_CLK>;
	status = "disabled";
};

/* AuPad debug board DTS или overlay */
&eud_com {
	status = "okay";
};
```

Для upstream предпочтителен отдельный debug configuration, а не включение root debug interface в обычном production board image.

### 5.2. I2 — SPI 189

DT описывает `interrupts = <GIC_SPI 189 IRQ_TYPE_LEVEL_HIGH>`, но Linux driver не запрашивает IRQ и работает polling. Автор сообщает, что interrupt не достигает GIC на SM6225.

До подтверждения маршрута следует выбрать один из вариантов:

- доказать работу interrupt, оставить property и реализовать IRQ с polling fallback;
- не указывать SPI 189 как рабочий interrupt в текущем SM6225 node и example.

Сам polling не является дефектом: это обоснованный workaround конкретного SoC. Binding может сохранить optional `interrupts` для других платформ, если существует подтверждённая hardware configuration.

### 5.3. I3 — статус ACK/hello protocol

Data ID `0x90`, ACK/hello ID `0x91`, payloads `0x06`/`0x05` и правило «host не отправляет следующий data packet до ACK» согласованы между AuPad host, stub, Linux и U-Boot.

Однако это project-specific protocol поверх Qualcomm EUD COM, а не продемонстрированный общий Qualcomm API. Compatible `qcom,eud-com` может описывать hardware block, но для upstream нужна отдельная спецификация transport policy:

- packet IDs и directions;
- ACK payload и момент отправки;
- hello format;
- RX/TX timeout и `PORT_RESET`;
- malformed packet handling;
- reconnect и recovery;
- совместимость с исходным Qualcomm host tool.

Без этого независимый host, использующий исторический Qualcomm `eud.py`, не обязан работать с AuPad serial protocol.

## 6. Обоснованные допущения, которые не следует считать ошибками

### 6.1. Non-posted MMIO

`ioremap_np` в полноценном Linux driver и `PROT_DEVICE_nGnRnE` для earlycon выбраны из-за потерь и повреждений пакетов при posted mapping. Это осмысленное platform-specific решение, подкреплённое аппаратными испытаниями автора.

Ручная замена `FIX_EARLYCON_MEM_BASE` при этом является ARM64/fixmap-specific. Generic [`earlycon.c`](https://github.com/torvalds/linux/blob/v7.3/drivers/tty/serial/earlycon.c) использует `set_fixmap_io()` и не предоставляет драйверу обычного параметра выбора memory attributes. Поэтому текущий подход допустим как bring-up workaround, но для upstream желательно согласованное arch/API решение, а не перенос этого кода на другие архитектуры.

### 6.2. Polling

Поскольку EUD interrupt на SM6225 не подтверждён, polling является правильным способом получить рабочий console. Pending host packet удерживается hardware, а project protocol запрещает следующий packet до ACK, поэтому polling не предполагает неизбежной потери RX.

Для generic driver можно позднее добавить IRQ mode с polling fallback, но не следует заменять polling на непроверенный IRQ-only path.

### 6.3. Фиксированные SM6225 parameters

Hardcoded register addresses, SCM calls, AP numbers, core topology и RPM ID в stub/OpenOCD scripts допустимы для khaje bring-up. Они не переносимы на другие SoC и должны быть отделены от reusable protocol code.

### 6.4. OpenOCD timings и enable cycling

SM6225-specific решения:

- default/effective SWD speed 7,5 MHz;
- снятие и повторная установка SWD enable;
- reset release;
- write gaps;
- delays после enable/open.

Они подкреплены наблюдениями автора, но не доказаны как требования других EUD implementations. В upstream их следует оформлять как проверенные generic fixes либо явные SM6225 quirks/configuration, а не менять поведение всех EUD devices только по результатам AuPad.

### 6.5. U-Boot ownership и handover

U-Boot serial driver предполагает, что предыдущая стадия уже включила EUD. Это прямо документировано и соответствует текущей загрузочной цепочке.

Сохранение PHY state при EUD on и использование `DM_FLAG_OS_PREPARE` для disconnect DWC3 gadget перед OS handover являются правильными архитектурными решениями. Их не нужно отменять; требуется лишь исправить более общий PHY lifecycle.

### 6.6. USB descriptors в host tools

Фиксированные endpoints `0x02`/`0x81`, configuration 1 и 16-byte records соответствуют наблюдаемому AuPad interface. Для единственного устройства это допустимое допущение.

Generic client должен:

- проверять VID и PID parent hub;
- находить нужную interface/configuration по descriptors;
- получать bulk IN/OUT endpoints из descriptors;
- проверять packet geometry;
- не предполагать, что другие EUD functions используют те же номера.

### 6.7. Root getty и debug access

`getty -n -l /bin/sh` на `ttyEUD0` даёт неаутентифицированный root shell. Для изолированного bring-up это осознанный и полезный выбор. В production image такая конфигурация недопустима без отдельной threat model и защиты debug interface.

## 7. Дополнительные улучшения

### 7.1. Console: nbcon как модернизация, а не обязательная ошибка

Текущая полноценная console использует legacy `.write`. Этот API остаётся поддерживаемым, поэтому само его использование не является нарушением.

Для качества panic/emergency output полезно рассмотреть nbcon:

- `write_atomic` для atomic/NMI-capable path;
- `write_thread` для task context;
- `device_lock`/`device_unlock` для синхронизации с UART hardware access;
- ownership/takeover semantics вместо ручного продолжения записи после failed trylock.

До такой миграции следует ограничить длительное spin-wait с отключёнными IRQ. Текущий count-based лимит `EUD_COM_TX_POLLS = 100000` не соответствует стабильному временному интервалу на разных частотах и с non-posted MMIO. Для полноценной console предпочтителен time-bounded atomic polling; earlycon должен сохранять небольшой детерминированный предел и отбрасывать вывод при недоступном host.

### 7.2. Suspend/resume и ownership

AuPad работает с отключённым suspend, поэтому отсутствие PM integration не мешает текущему сценарию. Generic driver должен определить:

- останавливается ли polling timer на suspend;
- сохраняются ли clocks для debug console;
- как восстанавливается COM state после resume;
- кто может включать и выключать глобальный EUD;
- как взаимодействуют COM console, SWD debugger, USB role switch и PHY.

Mainline [`qcom_eud.c`](https://github.com/torvalds/linux/blob/v7.3/drivers/usb/misc/qcom_eud.c) управляет enable state и USB role. AuPad COM использует другую register window, но зависит от того же глобального EUD/PHY state. Поэтому недостаточно просто добавить отдельный serial driver: требуется явная ownership/handover policy.

### 7.3. Host buffering и текстовая обработка

`Tx.pump()` продолжает читать pty input во время ожидания ACK. При постоянном записывающем client и остановленном target `Tx.buf` может расти без ограничения.

Следует добавить high-water mark и прекращать чтение master до отправки buffered data. Это перенесёт backpressure на pty writer.

Сейчас каждый COM payload декодируется отдельно. Многобайтовый UTF-8 символ, разделённый границей packet, будет повреждён при `errors="replace"`. Возможные решения:

- incremental UTF-8 decoder для текстового logger;
- байт-прозрачный pty output и отдельное текстовое представление для log;
- raw binary log параллельно с человекочитаемым log.

### 7.4. Разделение generic и platform-specific patches

Для OpenOCD целесообразно разделить работу на независимые series:

1. generic EUD robustness: parent-hub filtering, USB errors, endpoint cleanup;
2. SM6225 quirks и timings;
3. generic AArch64 `mrs` и `SP_EL0`;
4. khaje target configuration;
5. workflow scripts с явно локальными paths и recovery policy.

Для Linux уже существует полезное разделение на earlycon, PHY, binding, serial и DTS. Дополнительно можно вынести общие COM constants и packet helpers, чтобы earlycon и full driver не расходились в protocol details.

## 8. Приоритетный план исправлений

### P0 — текущая надёжность AuPad

1. Запретить комбинацию `keep_bootcon` и `console=ttyEUD0` на одном COM.
2. Ограничить ACK wait в stub и проверять hello.
3. Ограничить `eudlog.py resync()` и восстановить общий reconnect после любого disconnect.
4. Проверять COM length, record boundary и ACK payload.
5. Добавить raw logs и regression tests для этих сценариев.

### P1 — переносимость и подготовка upstream

1. Исправить PHY EUD on/off state machine.
2. Перевести SM6225 COM node в `status = "disabled"` и включать только в debug board configuration.
3. Разрешить противоречие между SPI 189 property и polling-only implementation.
4. Документировать ACK/hello protocol как стабильный interface.
5. Проверять OpenOCD/libusb errors и восстановление AArch64 mode.
6. Отделить SM6225 quirks от generic OpenOCD EUD behavior.
7. Определить PM и EUD ownership policy.

### P2 — качество и расширяемость

1. Рассмотреть nbcon migration.
2. Добавить descriptor-based USB discovery.
3. Добавить host backpressure и incremental decoding.
4. Реализовать IRQ mode только после подтверждения доставки interrupt.
5. Объединить duplicated COM helpers.
6. Добавить счётчики ошибок и статистику transport.

## 9. Рекомендуемые проверки после исправлений

### Host unit tests

- fragmented USB read внутри header и payload;
- short final record;
- length 0, 14, 15 и 255;
- truncated payload;
- ACK с неправильной length/payload;
- несколько records в одном read;
- UTF-8 symbol на границе packets;
- disconnect во время read, write, clear halt и NOP;
- reconnect после каждого disconnect point;
- bounded buffer при отсутствии ACK.

### Linux и Device Tree

- `W=1`, `sparse`, `smatch`;
- `dt_binding_check` и `dtbs_check` согласно [Writing Schema](https://docs.kernel.org/devicetree/bindings/writing-schema.html);
- early-only и full-console boot modes;
- отсутствие duplicate output после handover;
- console output одновременно с TTY input/output;
- host disconnect во время normal printk, oops и panic;
- повторные open/close `/dev/ttyEUD0`;
- suspend/resume, если эта функция будет включена.

### PHY transition tests

Отдельно проверить последовательности:

```text
EUD off → phy_init → phy_exit → phy_init
EUD on  → phy_init → phy_exit → phy_init при EUD on
EUD on  → phy_init → phy_exit → EUD off → phy_init
EUD off → phy_init → EUD on  → phy_exit → EUD off → phy_init
```

После каждого перехода необходимо проверять не только EUD link, но и нормальную USB peripheral/host работу.

### OpenOCD и аппаратные regression tests

- reconnect без hub reset;
- reconnect после endpoint halt;
- failed configuration и failed mode restoration;
- COM и SWD одновременно;
- repeated target halt/resume;
- panic last-line delivery;
- long COM RX/TX integrity run;
- сохранение raw logs и точных версий host tools, OpenOCD, kernel, U-Boot и stub.

## 10. Итоговая оценка

AuPad EUD code не является просто демонстрацией или набором упоминаний: он содержит реальные реализации COM и SWD и практические workaround’ы для SM6225. Non-posted MMIO, polling, PHY preservation и gadget disconnect перед handover являются обоснованными решениями.

Вместе с тем перед расширением кода на другие устройства или upstream необходимо устранить конкретные дефекты lifecycle и recovery, формализовать protocol и перенести platform assumptions из generic paths в конфигурацию конкретной платформы. До этих изменений правильная классификация результата: **ценная и технически содержательная SM6225-specific реализация с открытыми end-to-end компонентами, но ещё не универсальная реализация всех интерфейсов Qualcomm EUD**.

## 11. Основные источники

### AuPad

- [Проверенный repository tree](https://github.com/sleeply4cat/aupad-linux/tree/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c)
- [`tools/eudlog.py`](https://github.com/sleeply4cat/aupad-linux/blob/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/tools/eudlog.py)
- [`stub/main.c`](https://github.com/sleeply4cat/aupad-linux/blob/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/stub/main.c)
- [Linux patches](https://github.com/sleeply4cat/aupad-linux/tree/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/patches/linux)
- [U-Boot patches](https://github.com/sleeply4cat/aupad-linux/tree/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/patches/u-boot)
- [OpenOCD configuration и patch](https://github.com/sleeply4cat/aupad-linux/tree/72875cb9aef1021f9466c5bdf0abff3d9ff1a17c/tools/ocd)

### Linux и Device Tree

- [Linux Console API](https://docs.kernel.org/driver-api/tty/console.html)
- [DTS Coding Style](https://docs.kernel.org/devicetree/bindings/dts-coding-style.html)
- [Writing Devicetree Bindings in json-schema](https://docs.kernel.org/devicetree/bindings/writing-schema.html)
- [Linux v7.3 `earlycon.c`](https://github.com/torvalds/linux/blob/v7.3/drivers/tty/serial/earlycon.c)
- [Linux v7.3 `qcom_eud.c`](https://github.com/torvalds/linux/blob/v7.3/drivers/usb/misc/qcom_eud.c)
- [Linux v7.3 `phy-qcom-snps-femto-v2.c`](https://github.com/torvalds/linux/blob/v7.3/drivers/phy/qualcomm/phy-qcom-snps-femto-v2.c)
