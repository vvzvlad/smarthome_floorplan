# Отчёт по тест-стратегии — smarthome_floorplan — 2026-06-02

> Гибридное приложение: фронтенд Vue 3 + Vite + TypeScript (PWA) и бэкенд Python FastAPI,
> который раздаёт собранный фронтенд, мостит zigbee2mqtt по MQTT и защищён cookie-сессией.

## 1. Исполнительное резюме

- **Проанализировано модулей:** 8 (4 бэкенд + 4 фронтенд), по одному субагенту-аналитику на модуль.
- **Предложено тестов:** **60** — unit / integration / contract / E2E = **42 / 14 / 1 / 3** (unit = 70 %, E2E = 5 % и 3 ≤ 10 — пирамида соблюдена).
- **Отклонено как малоценные:** ~16 кандидатов (тривиальные геттеры, framework-wiring, тавтологичные snapshot-тесты, дублирующее покрытие — см. §7).
- **Покрытие сейчас (проверено инструментом):**
  - Бэкенд `pytest --cov`: **57 %** (api.py 71 %, mqtt_client.py 17 %, config_store.py 100 % строк, settings.py 100 % строк).
  - Фронтенд: **0 %** — тест-раннер вообще не настроен (нет vitest/jest, нет `test`-скрипта).
- **Прогноз после внедрения:** бэкенд ~90 %, фронтенд ~65 % строк в модулях с логикой (utils/store/извлечённые функции).

> **Сверка с заявлениями аналитиков (Фаза 4).** Аналитик `backend-config` оценил покрытие в ~75 %, но
> реальный прогон `pytest --cov` даёт **100 % строк** для `config_store.py` и `settings.py`. Это не
> противоречие: строки исполняются на happy-path, но **ветки и краевые случаи** (битый JSON, создание
> вложенных каталогов, парсинг `COOKIE_SECURE` из строки ENV) не проверяются. Предлагаемые для этих
> файлов тесты закрывают именно поведенческие/branch-пробелы и фиксируют контракт против регрессий, а не
> «добивают проценты строк». Заявления по `api.py` (~71 %) и `mqtt_client.py` (~17 %) подтверждены точно.

**Ключевой блокер:** ни один фронтенд-тест нельзя запустить, пока не добавлен раннер. Это предусловие №0 (см. §5).

---

## 2. Рекомендации по модулям

### backend-api (`server/src/api.py`, `server/main.py`) — текущее покрытие 71 %
- **Unit-тесты добавить:** нет (чистая логика этого модуля минимальна; `number_write_topics` тестируется в backend-mqtt — см. дедуп §7).
- **Integration-тесты добавить** (через `TestClient`, MQTT замокан):
  - `POST /api/config` — запись + условный рестарт MQTT-листенера ([api.py:122](server/src/api.py#L122)); ловит баг «всегда/никогда не перезапускать подписки».
  - `POST /api/mqtt/publish` — allow-list тем (403) + отклонение bool + коэрция числа в строку ([api.py:181](server/src/api.py#L181)); **самый рисковый непокрытый эндпоинт** (защита от публикации в произвольную тему).
  - `POST /api/entity/{id}/command` — валидация полей + оптимистичный merge не затирает соседние поля ([api.py:144](server/src/api.py#L144)).
  - `POST /api/login` — нестроковый/не-dict body → 401, а не 500; явная проверка успешного входа ([api.py:82](server/src/api.py#L82)).
- **НЕ тестировать:** `main.py` (uvicorn bootstrap), `GET /api/info`, `GET/DELETE /api/icon` happy-path, `logout`, `lifespan`, статический mount — framework-wiring / уже покрыто (см. §7).

### backend-mqtt (`server/src/mqtt_client.py`) — текущее покрытие 17 % (наименее покрытый бэкенд-модуль)
- **Кандидаты на извлечение в чистые функции:** разбор сообщения и слияние состояния внутри `mqtt_listener_loop` ([mqtt_client.py:71-95](server/src/mqtt_client.py#L71-L95)) → `update_device_state(...)` / `update_topic_value(...)`; сборка payload ([mqtt_client.py:106](server/src/mqtt_client.py#L106), [:118](server/src/mqtt_client.py#L118)) → `build_command_payload` / `build_value_payload`.
- **Unit-тесты добавить:** `number_read_topics` ([:27](server/src/mqtt_client.py#L27)) и `number_write_topics` ([:39](server/src/mqtt_client.py#L39)) — краевые случаи (нет `numberConfig`, пустой/непустой topic, не-number типы; от них зависит security-allow-list); `_make_client_kwargs` ([:18](server/src/mqtt_client.py#L18)) — наличие/отсутствие учётных данных; извлечённые `update_device_state` (битый JSON не падает, не-dict игнорируется, замена vs merge), `update_topic_value` (не-UTF8 не роняет); `build_command_payload` (`state.upper()`).
- **Integration-тесты добавить** (фейковый in-memory aiomqtt-клиент): `mqtt_listener_loop` — подписка на `zigbee2mqtt/#` + темы конфига, мутация кэшей, ветка reconnect с замоканным `asyncio.sleep`; три `publish_*` — точная пара `(topic, payload)` (сейчас всюду замоканы, реальные тела не проверяются нигде).
- **НЕ тестировать:** ленивые `import aiomqtt`, внутренности `aiomqtt.Client`, логирование — реализация/сторонняя библиотека.

### backend-config (`server/src/config_store.py`, `server/src/settings.py`) — 100 % строк, но есть branch-пробелы
- **Unit-тесты добавить:** `read_config` на **битом JSON** ([config_store.py:12-13](server/src/config_store.py#L12-L13)) — фиксирует контракт (сейчас падает на 3 вызывающих сайтах); `write_config` в **несуществующий вложенный каталог** ([:19](server/src/config_store.py#L19)) — ветка `mkdir(parents=True)` (в проде `data/` — свежий volume); roundtrip с **не-ASCII** именами ([:21](server/src/config_store.py#L21)); `COOKIE_SECURE` парсинг строки ENV `"false"/"0"/"1"` → bool ([settings.py:30](server/src/settings.py#L30)); **раздельная** проверка обязательности `AUTH_PASSWORD` и `MQTT_HOST` ([:8](server/src/settings.py#L8),[:13](server/src/settings.py#L13)).
- **НЕ тестировать:** `effective_secret_key`, `_normalize_log_level`, default-config литерал, singleton `Settings()`, движок pydantic-settings — уже покрыто / сторонняя библиотека.

### frontend-utils (`src/utils/*.ts`) — 0 %, наивысший ROI
- **Кандидаты на извлечение:** cover-fit математика в `image.ts` ([:21-24](src/utils/image.ts#L21-L24)) → `computeCoverFit(imgW,imgH,size)`.
- **Unit-тесты добавить:** `extractJsonPath` ([textEntity.ts:1](src/utils/textEntity.ts#L1)) — null-обход, prototype-ключи, индексы массива; `formatTextValue` ([:10](src/utils/textEntity.ts#L10)) — значения `0/false` не должны превращаться в «—»; **`needsMigration`** ([configMigration.ts:62](src/utils/configMigration.ts#L62)) — матрица из ~9 веток; **`migrateConfig`/`migrateEntityColors`** ([:45](src/utils/configMigration.ts#L45),[:15](src/utils/configMigration.ts#L15)) — матрица из ~10 веток (дефолты цветов, удаление старых ключей, идемпотентность); `computeCoverFit` (cover vs letterbox, центрирование, нулевые размеры).
- **Integration-тесты добавить** (замоканный `fetch`): `sendCommand` — `encodeURIComponent` в пути (защита от инъекции) ([api.ts:37](src/utils/api.ts#L37)); `checkSession` — true/false/сеть-упала/битый JSON ([:75](src/utils/api.ts#L75)); `apiFetch` 401 → `window.location.reload()` ровно один раз + merge заголовков ([:9-13](src/utils/api.ts#L9-L13)).
- **Property-based (fast-check):** идемпотентность `migrateConfig(migrateConfig(x)) == migrateConfig(x)` и `needsMigration(...) == false` после миграции — самый ценный инвариант.
- **НЕ тестировать:** `login`/`logout` (проброс), `apiFetch` напрямую (внутренний), растровый вывод `resizeImageToPng` (Canvas — недетерминирован в jsdom).

### frontend-store (`src/stores/floorplan.ts`) — 0 %, второй по ROI
- **Unit-тесты добавить** (`setActivePinia(createPinia())`, `api` замокан, fake timers): `setTopicValues` (epsilon-сверка, NaN, скип) — самый сложный метод ([:156](src/stores/floorplan.ts#L156)); `toggleEntityState` (оптимистичный флип, **нет отката** при ошибке — задокументировать) ([:117](src/stores/floorplan.ts#L117)); `setNumberValue` (пустой writeTopic → ранний выход) ([:134](src/stores/floorplan.ts#L134)); `setEntityState` (таблица `shouldLightUp`, исключение `idle`) ([:145](src/stores/floorplan.ts#L145)); `addEntity` (text/number конфиги по типу) ([:42](src/stores/floorplan.ts#L42)); `duplicateEntity` (clamp +3, deep-clone) ([:86](src/stores/floorplan.ts#L86)); `removeEntity`/`updateEntity`/`loadConfig`/`clearConfig`/`selectedEntity`; **debounced auto-save** watcher — коалесценция при быстрых правках ([:31-36](src/stores/floorplan.ts#L31-L36)).
- **НЕ тестировать:** `setBaseImage`, getter `entities`, голые `ref`-экспорты, сами `saveConfig/sendCommand/publishRaw` — тривиально / другой модуль.

### frontend-editor-components (`src/components/editor/*.vue`) — 0 %
- **Кандидаты на извлечение в чистые функции** (центр тяжести, → `src/utils/coords.ts` + композаблы): `toImagePercent` (дублируется 4× в [CanvasArea.vue:40](src/components/editor/CanvasArea.vue#L40) и [EntityOverlay.vue:53](src/components/editor/EntityOverlay.vue#L53)); `clampZoom` ([CanvasArea.vue:25](src/components/editor/CanvasArea.vue#L25)); `dragDeltaPercent` (дублируется 4×, расхождение в guard /0 — [:53](src/components/editor/EntityOverlay.vue#L53) vs [:148](src/components/editor/EntityOverlay.vue#L148)); `entityStyle` ([EntityOverlay.vue:221](src/components/editor/EntityOverlay.vue#L221)); `resolveNumberDisplay` ([:275](src/components/editor/EntityOverlay.vue#L275)); `labelTransform`; `pointsToSvgString`; ops точек; `filterDevices` ([PropertiesPanel.vue:121](src/components/editor/PropertiesPanel.vue#L121)); `parseNumberField` ([:172](src/components/editor/PropertiesPanel.vue#L172)); фабрики дефолт-конфигов.
- **Unit-тесты добавить:** по одному на каждую извлечённую функцию (см. §5, prerequisite-расширения). `resolveNumberDisplay` — **общий** с viewer (дедуп: тестируется один раз).
- **Integration-тесты добавить** (@vue/test-utils + `createTestingPinia`): `onTypeChange` не затирает существующий конфиг + emit `toggle-draw-mode` ([PropertiesPanel.vue:144](src/components/editor/PropertiesPanel.vue#L144)).
- **НЕ тестировать:** обёртки file-input/FileReader, проброс в store-методы, v-model биндинги, SVG-разметку/градиенты — wiring / тавтологичный snapshot.

### frontend-viewer-components (`InteractiveFloorplan.vue`, `LoginForm.vue`, `HelloWorld.vue`) — 0 %
- **Кандидаты на извлечение** (→ `src/utils/numberWidget.ts`): `computeNextStep`, `roundToStep` ([InteractiveFloorplan.vue:172](src/components/common/InteractiveFloorplan.vue#L172)), `resolveNumberValue` ([:162](src/components/common/InteractiveFloorplan.vue#L162)), `isAtMin/isAtMax` ([:218](src/components/common/InteractiveFloorplan.vue#L218)); `brightnessTo*Opacity` ([:84](src/components/common/InteractiveFloorplan.vue#L84),[:112](src/components/common/InteractiveFloorplan.vue#L112)).
- **Unit-тесты добавить:** `computeNextStep` (clamp у границ, инвертированный min/max, нулевой/отрицательный шаг, no-op→null); `roundToStep` (дрейф float, экспоненциальный шаг `1e-7`); `resolveNumberValue` (приоритет optimistic>topic>min, `0` побеждает); `isAtMin/isAtMax`; `brightnessTo*Opacity` (две **расходящиеся** формулы — задокументировать или унифицировать).
- **Integration-тесты добавить** (@vue/test-utils): степпер числа — клик «+» эмитит `entity-set-value` с верным `writeTopic`, у границы emit подавляется ([:285](src/components/common/InteractiveFloorplan.vue#L285)); `LoginForm.submit` — success/wrong-password/network-error + disabled при pending ([LoginForm.vue:11](src/components/LoginForm.vue#L11)); state-машина click-vs-long-press (fake timers, порог 10px/500ms) ([:33](src/components/common/InteractiveFloorplan.vue#L33)).
- **НЕ тестировать / УДАЛИТЬ:** **`HelloWorld.vue` — мёртвый код** (0 ссылок в `src`, не менялся со скаффолда) → удалить, не тестировать. CSS-style-билдеры позиций — тавтологичный snapshot.

### frontend-app-shell (`App.vue`, `router/index.ts`, `views/*`, `main.ts`) — 0 %
- **Кандидаты на извлечение:** нормализация состояния `'ON'→'on'` ([App.vue:18-20](src/App.vue#L18-L20)) → `normalizeEntityState(payload)` (**консолидировать** с дублем в store [floorplan.ts:145](src/stores/floorplan.ts#L145)).
- **Unit-тесты добавить:** `normalizeEntityState` ('ON'/'on'→'on'; 'OFF'/undefined/число/не-строка→'off').
- **Integration-тесты добавить** (mount App, `api` замокан, `createTestingPinia`): auth-gate — `checkSession`→false рендерит `LoginForm`, →true рендерит header+RouterView ([App.vue:81-95](src/App.vue#L81-L95)) — наивысший ROI модуля; миграция конфига при загрузке ([:35-42](src/App.vue#L35-L42)).
- **НЕ тестировать:** `main.ts`, `router/index.ts` (таблица маршрутов без guard), `ViewerView.vue`/`EditorView.vue` (тонкие обёртки), polling-leak и logout-reload — framework-wiring (крупнейшая skip-секция модуля).

---

## 3. Сквозные аспекты

- **Contract-тесты:** один — payload, публикуемый в zigbee2mqtt, против `<base>/<name>/set`-схемы (`{"state":"ON|OFF"}` / `{<field>:<number>}`, [mqtt_client.py:106](server/src/mqtt_client.py#L106)). Ловит дрейф моста относительно контракта z2m. HTTP-граница фронт↔бэк проверяется на integration-уровне с обеих сторон (api.ts ↔ TestClient), отдельный pact не нужен.
- **Property-based (fast-check):** идемпотентность `migrateConfig`; `extractJsonPath` никогда не бросает на случайных путях; `formatTextValue` корректно подставляет любое непустое значение; `computeCoverFit` всегда даёт `w≥size && h≥size`.
- **Дымовые E2E (≤3, см. §6):** только именованные пользовательские сценарии.
- **Test-data factories нужны:** `makeFloorplanConfig(overrides)` и `makeEntity(type, overrides)` (Vue) + pytest-фикстуры конфигов (битый/старый-формат/не-ASCII) — переиспользуются почти всеми наборами.

## 4. Обнаруженные антипаттерны

- **Глобальные мутабельные синглтоны** `device_states`/`topic_values` ([mqtt_client.py:12](server/src/mqtt_client.py#L12),[:15](server/src/mqtt_client.py#L15)) — порядко-зависимое состояние; тесты обязаны чистить (`device_states.clear()` в conftest:23); `topic_values` сейчас **не сбрасывается** между тестами → потенциальная утечка.
- **Replace-vs-merge несогласованность:** листенер целиком заменяет запись устройства ([mqtt_client.py:87](server/src/mqtt_client.py#L87)), а API мержит поля ([api.py:171](server/src/api.py#L171)) — обновление от брокера может затереть оптимистичное поле.
- **Fire-and-forget без отката:** `toggleEntityState`/`setNumberValue` применяют оптимистичное состояние и глотают ошибку команды ([floorplan.ts:129](src/stores/floorplan.ts#L129)) — UI показывает состояние, которого у устройства нет.
- **Скрытый сетевой побочный эффект:** `watch(config,...)` ставит debounce-автосейв на любую мутацию конфига ([floorplan.ts:31-36](src/stores/floorplan.ts#L31-L36)) — «чистые» экшены неявно ходят в сеть.
- **God-компонент + прямой DOM между сиблингами:** `CanvasArea.vue` смешивает upload/zoom/polygon/drag; `document.querySelector('.image-wrapper')` из компонентов ([CanvasArea.vue:35](src/components/editor/CanvasArea.vue#L35), [EntityOverlay.vue:46](src/components/editor/EntityOverlay.vue#L46)); `window.addEventListener` без `onUnmounted`-страховки (утечка слушателей при размонтировании в процессе drag).
- **Логика в шаблоне:** `getSvgAspectRatio()`/`getEntityValues()` с `getBoundingClientRect` вызываются внутри `v-for` на каждый рендер ([CanvasArea.vue:200](src/components/editor/CanvasArea.vue#L200)).
- **Дублирование:** drag-математика 4×, координатный transform 3-4× — уже разошлись в guard на /0.
- **Две расходящиеся формулы яркость→прозрачность** ([InteractiveFloorplan.vue:85](src/components/common/InteractiveFloorplan.vue#L85) vs [:117](src/components/common/InteractiveFloorplan.vue#L117)).
- **`as any` и пустой `catch`** в `App.vue` ([:35](src/App.vue#L35),[:64](src/App.vue#L64)); `window.location.reload()` как управляющий поток (logout, 401).
- **Мёртвый код:** `HelloWorld.vue`.
- **Нестабильных тестов нет** (тестов фронтенда не существует; бэкенд — 20 тестов, в CI зелёные, история флака отсутствует).

## 5. Необходимые рефакторинги перед написанием тестов

- **PRE-0 (блокер всего фронтенда):** добавить раннер — `vitest` + `@vue/test-utils` + `jsdom` + `@vitest/coverage-v8` (+ `fast-check`, `@pinia/testing` по желанию), блок `test` в `vite.config.ts` (`environment:'jsdom'`, `globals:true`) и скрипты `test`/`coverage`. **Блокирует:** все фронтенд-тесты.
- **R-utils:** извлечь `computeCoverFit` из `image.ts`. Блокирует: unit cover-fit + property P4.
- **R-mqtt:** извлечь `update_device_state`/`update_topic_value`/`build_*_payload`; внедрить фабрику клиента и backoff. Блокирует: unit стейт-мерджа и payload, integration листенера и publish.
- **R-editor:** извлечь ~11 чистых функций в `src/utils/coords.ts` + композаблы (`toImagePercent`, `clampZoom`, `dragDeltaPercent`, `entityStyle`, `resolveNumberDisplay`, `labelTransform`, `pointsToSvgString`, point-ops, `filterDevices`, `parseNumberField`, фабрики). Блокирует: 10 unit редактора.
- **R-viewer:** извлечь `src/utils/numberWidget.ts` + `brightnessTo*Opacity`. Блокирует: 5 unit вьюера.
- **R-shared:** консолидировать дублирующиеся `resolveNumberValue`/`resolveNumberDisplay` (editor↔viewer) и `normalizeEntityState` (App.vue↔store) в одну тестируемую точку. Блокирует: устранение дублей перед фиксацией тестами.

## 6. План внедрения (по фазам)

- **Фаза 1 — Бэкенд, без рефакторинга (наивысший ROI/усилие).** backend-api integration (4) + backend-config edge unit (5). Закрывает security-allow-list `/api/mqtt/publish`, условный рестарт листенера и поведение на битом конфиге. Покрытие бэкенда 57 %→~80 % без изменения кода.
- **Фаза 2 — PRE-0 + frontend-utils + store.** Поднять Vitest, затем чистые `configMigration`/`textEntity`/`computeCoverFit` (5 unit + property) и store (12 unit, fake timers). Максимальный возврат на новый раннер: вся бизнес-логика фронта под тестом.
- **Фаза 3 — backend-mqtt (рефакторинг R-mqtt).** Извлечь чистые ядра, добавить unit (6) + integration с фейковым клиентом (2) + contract (1). Поднимает самый «слепой» модуль с 17 %.
- **Фаза 4 — Извлечения компонентов (R-editor/R-viewer/R-shared) + unit.** Координаты/zoom/drag/number-widget/opacity (15 unit). Устраняет дублирование и фиксирует математику.
- **Фаза 5 — Компонентные integration + E2E.** auth-gate App.vue, `LoginForm.submit`, степпер числа, `onTypeChange`; затем 3 дымовых E2E:
  1. **Логин → просмотр → переключение устройства** (login → ViewerView → клик по сущности → команда ушла).
  2. **Редактор: загрузка изображения → размещение сущности → сохранение → перезагрузка сохраняет конфиг.**
  3. **Number-виджет: шаг значения публикует корректную тему/значение.**

## 7. Источники

- Отчёты **8** субагентов-аналитиков (`module-testability-analyst`), по одному на модуль.
- Вывод coverage-инструмента: `pytest --cov=server/src` → TOTAL **57 %** (api 71 / mqtt 17 / config_store 100 / settings 100); фронтенд — раннера нет, **0 %**.
- Независимая проверка: `HelloWorld.vue` — 0 ссылок в `src` (мёртвый код); `package.json` — отсутствие vitest/jest/test-utils и `test`-скрипта; `vite.config.ts` — нет `test`-блока.
- **Фильтрация тестов:**
  - Шаг 1 (кросс-модульный дедуп): объединены `number_*_topics` (api→mqtt), `resolveNumberValue`/`resolveNumberDisplay` (editor↔viewer), `normalizeEntityState` (App↔store), `formatTextValue` (компоненты→utils) — снято ~5 дублей.
  - Шаг 2 (skip-list): отброшены тривиальные геттеры, framework-wiring (`main.ts`, router, тонкие views), уже покрытые happy-path, тавтологичные snapshot, сторонние библиотеки — ~16 кандидатов.
  - Шаг 3 (пирамида): набор подрезан до unit 42 / integration 14 / contract 1 / E2E 3 (unit 70 %, E2E 5 % ≤ 10).
  - Шаг 4 (refactor-blocking): фронтенд-тесты помечены зависящими от PRE-0 и извлечений (§5).
  - Шаг 5 (ROI): порядок внедрения — сначала бэкенд без рефакторинга, затем utils/store, затем извлечения.
  - Шаг 6 (adversarial): каждый оставшийся тест проверен вопросом «упадёт ли он при реалистичной поломке?» — отклонены snapshot-тесты и проверки v-model как проходящие при сломанной логике.
