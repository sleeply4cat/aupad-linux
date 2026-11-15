# Подпись модифицированного ABL: исследование, поиск ключей в утечках и проверка результата

**Дата:** 14 ноября 2026 года
**Предмет:** можно ли подписать модифицированный загрузчик (ABL с unlock-патчем из [Разблокировка_загрузчика_исследование.md](Разблокировка_загрузчика_исследование.md)) так, чтобы его приняла цепочка доверия устройства; формат sec image v8; поиск приватных ключей в публичных зеркалах/утечках. Планшет не трогался — всё собрано и проверено офлайн.
**Материал:** `~/111/backups/aupad-20261112/abl_a.bin`, `~/Downloads/prog_firehose_ddr.elf` (тот же firehose, что используется для EDL), публичное зеркало sectools.

## 1. Вердикт (главная таблица)

| Вопрос | Ответ | Доказательство |
|---|---|---|
| Схема подписи стокового ABL | **Полностью откалибрована**: оригинальная подпись верифицируется | RSA-PSS(SHA-256, salt 32) над `file[0x1000:0x1138]` (метаданные+vhash+hashtable), pubkey leaf «SecTools Test User» → `Verified OK` |
| Можно ли собрать и подписать модифицированный ABL | **Да** — и не просто «формально валидный», а **подлинной тестовой цепочкой Qualcomm** | финальный `abl_patched_testsigned.bin`: CA и root в образе **байт-в-байт** совпадают с цепочкой самого планшета; leaf выпущен подлинным CA-ключом; подпись leaf-ключом проверяется из образа |
| Откуда ключи | **Приватные ключи тестовой пары QC root+CA идут публично в составе sectools** | зеркало `github.com/basehub/sectools` → `resources/data_prov_assets/Signing/Local/qc_presigned_certs-key2048_exp65537_paddingPSS/{qpsa_rootca,attestca}.{cer,key}` — сертификаты байт-в-байт совпали с цепочкой ABL планшета и firehose-лоадера; ключи нешифрованные |
| Это «утечка»? | **Нет** — штатные тестовые ключи Qualcomm («General Use Test Key (for testing only)»), лежат в открытых дистрибутивах sectools с 2015 года (root/CA notBefore 2015-09-10) | `config.xml`: `root_pre=True`, `attest_ca_pre=True` — предвыпущенные ключи, прилагаемые к инструменту |
| Оригинальный leaf ABL действительно выпущен этим CA? | **Да** | `openssl verify -CAfile qc_root.pem -untrusted qc_ca.pem cert1.der` → OK; leaf firehose-лоадера → тоже OK |
| Тамpering-защита | работает | 1 битый байт в FV → слот SHA-384 расходится; обновлённый covered со старой подписью → `Verification failure` |
| Что осталось неизвестным | примет ли XBL образ — зависит от состояния secboot на устройстве (офлайн не определить); root цепочки совпадает с тем, что и так зашит в его ABL, так что при активном secboot образ **должен** проходить | проверка только на устройстве (вне рамок задачи) |

## 2. Формат sec image v8 (откалиброван на оригинале)

| Что | Где в abl_a.bin | Значение |
|---|---|---|
| ELF-обёртка | 0x0–0x3000 | ELF32 AArch64, 3 phdr: NULL, hash-сегмент (0x1000, 0x1a38), LOAD (0x3000, 0x32000) |
| Метаданные | 0x1000–0x10a8 (0xA8) | 0x1990 = размер за метаданными, 0x90 = размер hash-таблицы (3×48), 0x1800 = размер области сертов+паддинга (0x1238→0x2A38), 0x02 = число слотов, 0x3000 = смещение LOAD |
| vhash | 0x10a8 | **SHA-384**(ELF header + program headers = file[0:0x94]) |
| Слоты сегментов | 0x10d8 (нули), 0x1108 | NULL-сегмент → нули; LOAD → **SHA-384**(file[0x3000:0x35000]) |
| Подпись образа | 0x1138–0x1238 (256 Б) | **RSASSA-PSS**(SHA-256, MGF1-SHA256, salt 32) над file[0x1000:0x1138] |
| Цепочка сертов | 0x1238–0x1F37 | leaf ← CA ← root, RSA-2048, серты PSS; leaf: BC CA:FALSE pathlen:0, KU DigitalSignature, EKU CodeSigning; CA: CA:TRUE pathlen:0; root: self-signed CA:TRUE |
| LZMA-контейнер | 0x3078 | props 0x5D, dict 0x01000000, **usize = точный размер** (оригинал: 0x7d0c8); поток liblzma ALONE (+EOPM); внутри inner FV (0x7d0c8): FFS f536d559 → RAW «LinuxLoader» + PE32 (0x7d000), PE с 0xb8 |
| FFS-контрольные суммы | 0x3048 | attrs=0 → file checksum 0xAA; header checksum = (0x100 − Σ header с обнулёнными IntegrityCheck/State) & 0xFF (подтверждено на оригинале: 0xcb) |

## 3. Поиск ключей: трасса

| Шаг | Результат |
|---|---|
| Локальный `prog_firehose_ddr.elf` (EDL-лоадер планшета) | в его hash-сегменте та же цепочка: CA `sha256 89013cd7…` и root `f8ab2052…` **байт-в-байт** равны сертам ABL; leaf другой (per-build «SecTools Test User») → пара Root+CA фиксированная |
| Поиск публикаций той же пары | [разбор Onyx Boox](https://overtone.codeberg.page/onyx-boox-note-air5-c/boot/secure-boot.html) — у другого вендора те же имена цепочки (там ECDSA-вариант); [unoq-baremetal](https://github.com/paulober/unoq-baremetal/blob/main/docs/boot-chain.md) — firehose с этой тестовой цепочкой, secdata пуст, unsigned code выполняется |
| Зеркало sectools | `github.com/basehub/sectools` (63 МБ, полный инструмент); в `resources/data_prov_assets/Signing/Local/` — **директории с готовыми парами ключ+серт** |
| Совпадение | папка `qc_presigned_certs-key2048_exp65537_paddingPSS`: `qpsa_rootca.cer` = root ABL (sha256 `f8ab2052…4e861`), `qpsa_attestca.cer` = CA ABL (`89013cd7…af4d0f`) — байт-в-байт; `sha256rootcert.txt` подтверждает; `qpsa_{rootca,attestca}.key` — RSA-2048 PEM **без пароля**, модули сходятся с сертами |
| Замыкание | оригинальный leaf ABL и leaf firehose верифицируются через этот root+CA (`openssl verify` OK) — мы владеем ключами, которыми выпущены серты устройства |
| Выпуск нашего leaf | leaf «SecTools Test User» (профиль оригинала: AKI/BC CA:FALSE pathlen:0/KU digitalSignature/EKU codeSigning, PSS) подписан подлинным `qpsa_attestca.key`; в образе лежат [наш leaf, подлинный CA, подлинный root] |

## 4. Батарея проверки валидности финального образа

| № | Проверка | Результат |
|---|---|---|
| 1 | Оригинальная подпись vs оригинальный leaf (калибровка схемы) | `Verified OK` |
| 2 | Подпись нового образа vs наш leaf-ключ | `Verified OK` |
| 3 | Подпись нового образа vs **leaf, извлечённый из самого образа** | `Verified OK` |
| 4 | CA и root в образе байт-в-байт = серты оригинального ABL (`89013cd7…`, `f8ab2052…`) | True/True |
| 5 | Цепочка из образа: `openssl verify -show_chain` | OK, depth 0→2, root = «Generated Test Root CA» |
| 6 | leaf из образа vs **подлинный root+CA** | OK |
| 7 | vhash и слот LOAD пересчитаны | совпадают |
| 8 | LZMA roundtrip (inner FV, патч на месте @PE 0x47da4) | OK |
| 9 | FFS/section размеры и чексуммы | OK (0x251b3 / 0x2519b) |
| 10 | Неизменность ELF hdr+phdrs, метаданных, хвоста раздела | байт-в-байт |
| 11 | Негативный контроль (тампер FV; обновлённый covered + старая подпись) | детектируется |

Отличие от предыдущей итерации (с локальной цепочкой «AuPad Local Test»): ранее образ был формально валидным, но с чужим root; теперь цепочка совпадает с вендорской вплоть до root, т.е. XBL, проверяющий подпись, видит знакомую цепочку доверия.

## 5. Ограничения и что это значит для планшета

| Пункт | Суть |
|---|---|
| Secboot-состояние устройства | офлайн не определить; если secboot активен и root-хэш во фьюзах соответствует «Generated Test Root CA» (что почти наверняка — ABL самого устройства подписан именно этой цепочкой), наш образ должен пройти проверку; если secboot выключен — пройдёт что угодно |
| Этическая сторона | ключи — штатные тестовые материалы Qualcomm, публично распространяются внутри его же инструмента; использование — стандартная практика (ср. [qtestsign](https://github.com/msm8916-mainline/qtestsign)); это не «взлом» production-ключей вендора |
| Проверка на устройстве | вне рамок задачи (на планшет ничего не записывалось); безопасная точка — неактивный слот abl_b при готовности EDL-отката |
| Дубликат метаданных | поле «cert region» (0x1800) описывает размер от начала сертов до конца сегмента — при сохранении раскладки метаданные остаются валидными при любом размере нашей цепочки |

## 6. Артефакты

| Путь | Что |
|---|---|
| `/tmp/ablwork/signed/abl_patched_testsigned.bin` | **итоговый образ v2** — патченный ABL, подписанный подлинной тестовой цепочкой QC (1 МиБ, размер раздела) |
| `/tmp/ablwork/signed/{sig.bin, covered.bin, leaf/ca/root.der}` | подпись, покрываемые данные, серты из образа |
| `/tmp/ablwork/qcchain/{leaf.key,leaf.der,ca.cer,root.cer}` | наш leaf (выпущен подлинным CA), подлинные CA/root |
| `/tmp/ablwork/{qc_ca.pem,qc_root.pem}`, `/tmp/ablwork/certs/cert{1,2,3}.der` | PEM-копии подлинной пары; оригинальная цепочка ABL |
| `/tmp/ablwork/firehose/c*.der` | цепочка из `prog_firehose_ddr.elf` |
| `/tmp/leaksearch/sectools-mirror/` | клон `github.com/basehub/sectools` (источник ключей) |
| `/tmp/zscripts/sign_abl.py` | сборщик end-to-end (патч → repack → хэши → подпись подлинной цепочкой), самопроверки внутри |

## 7. Открытые вопросы

| Вопрос | Как закрыть |
|---|---|
| Состояние secboot на планшете (фьюзы) | только на устройстве; при активном secboot наш образ с подлинной цепочкой должен проходить |
| Мини-риски LZMA-декодера (usize/EOPM) | оригинал и наш образ структурно идентичны (точный usize + поток liblzma); подтвердится той же загрузкой неактивного слота |
| ECDSA-варианты той же пары (как у Boox) | в том же зеркале sectools есть другие папки (`sha1_certs…`, `mrc_presigned…`) — не требовалось |
