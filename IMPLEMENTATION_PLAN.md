# План реализации: Smart Home Floorplan

## Обзор архитектуры

```
[Browser] ←HTTP/Basic Auth→ [FastAPI сервер]
                                    ↕ MQTT
                             [Zigbee2MQTT / broker]

Сервер:
- раздаёт собранный фронтенд как static files
- хранит конфиг планировки на диске (config.json)
- подключается к MQTT, слушает z2m топики, хранит последнее состояние устройств в памяти
- принимает команды от фронтенда и пересылает их в MQTT
```

### Формат entity ID

В конфиге планировки поле `entityId` — это **friendly_name** устройства в Zigbee2MQTT.  
Например: `"Living Room Light"`, `"Kitchen Switch"`.

### Z2M топики

| Направление | Топик | Payload |
|---|---|---|
| Слушаем (состояние) | `zigbee2mqtt/{friendly_name}` | `{"state": "ON", ...}` |
| Публикуем (команда) | `zigbee2mqtt/{friendly_name}/set` | `{"state": "ON"}` |

---

## Часть 1: Python сервер

### Структура файлов

```
server/
  main.py
  requirements.txt
  src/
    __init__.py
    api.py
    mqtt_client.py
    config_store.py
```

---

### `server/requirements.txt`

```
fastapi
uvicorn[standard]
aiomqtt
python-multipart
```

---

### `server/main.py`

Точка входа, аналогично label_maker:

```python
import os
import uvicorn

def main():
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.api:app", host="0.0.0.0", port=port, reload=False)

if __name__ == "__main__":
    main()
```

---

### `server/src/__init__.py`

Пустой файл.

---

### `server/src/config_store.py`

Отвечает за чтение/запись конфига планировки на диск.

```python
import json
import os
from pathlib import Path

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "/data/config.json"))

def read_config() -> dict:
    """Читает конфиг с диска. Если файла нет — возвращает пустой конфиг."""
    if not CONFIG_PATH.exists():
        return {"id": "", "name": "New Floorplan", "imageBase64": "", "entities": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def write_config(config: dict) -> None:
    """Сохраняет конфиг на диск, создаёт директорию если нужно."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
```

---

### `server/src/mqtt_client.py`

MQTT клиент на aiomqtt. Подписывается на `zigbee2mqtt/#`, хранит последнее состояние устройств в памяти.

```python
import asyncio
import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Глобальный словарь состояний: { friendly_name: { "state": "ON"|"OFF", ... } }
device_states: Dict[str, Dict[str, Any]] = {}

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", None)
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", None)
Z2M_BASE = "zigbee2mqtt"

async def mqtt_listener_loop():
    """Запускается в фоне при старте приложения. Слушает z2m топики и обновляет device_states."""
    import aiomqtt
    while True:
        try:
            async with aiomqtt.Client(
                hostname=MQTT_HOST,
                port=MQTT_PORT,
                username=MQTT_USERNAME,
                password=MQTT_PASSWORD,
            ) as client:
                logger.info(f"MQTT connected to {MQTT_HOST}:{MQTT_PORT}")
                await client.subscribe(f"{Z2M_BASE}/#")
                async for message in client.messages:
                    topic = str(message.topic)
                    # Игнорируем служебные топики z2m (bridge/...) и топики /set /get
                    parts = topic.split("/")
                    if len(parts) != 2:
                        continue
                    _, friendly_name = parts
                    try:
                        payload = json.loads(message.payload)
                        if isinstance(payload, dict) and "state" in payload:
                            device_states[friendly_name] = {
                                "state": payload["state"]  # "ON" или "OFF"
                            }
                    except (json.JSONDecodeError, Exception):
                        pass
        except Exception as e:
            logger.warning(f"MQTT connection lost: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)


async def publish_command(friendly_name: str, state: str) -> None:
    """Публикует команду в z2m топик {friendly_name}/set."""
    import aiomqtt
    async with aiomqtt.Client(
        hostname=MQTT_HOST,
        port=MQTT_PORT,
        username=MQTT_USERNAME,
        password=MQTT_PASSWORD,
    ) as client:
        topic = f"{Z2M_BASE}/{friendly_name}/set"
        payload = json.dumps({"state": state.upper()})
        await client.publish(topic, payload)
        logger.info(f"MQTT publish: {topic} -> {payload}")
```

---

### `server/src/api.py`

FastAPI приложение. Basic Auth через Depends. Все API роуты требуют авторизации. Статика фронтенда монтируется последней.

```python
import asyncio
import os
import secrets
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

from .config_store import read_config, write_config
from .mqtt_client import device_states, mqtt_listener_loop, publish_command

logger = logging.getLogger(__name__)

AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "changeme")
AUTH_USERNAME = "admin"  # фиксированный логин

security = HTTPBasic()


def verify_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """Проверяет Basic Auth. Бросает 401 если неверно."""
    username_ok = secrets.compare_digest(credentials.username.encode(), AUTH_USERNAME.encode())
    password_ok = secrets.compare_digest(credentials.password.encode(), AUTH_PASSWORD.encode())
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Запускаем MQTT listener в фоне при старте
    task = asyncio.create_task(mqtt_listener_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)


@app.get("/api/config", dependencies=[Depends(verify_auth)])
def get_config():
    return JSONResponse(content=read_config())


@app.post("/api/config", dependencies=[Depends(verify_auth)])
async def post_config(request: Request):
    body = await request.json()
    write_config(body)
    return JSONResponse(content={"ok": True})


@app.get("/api/states", dependencies=[Depends(verify_auth)])
def get_states():
    """Возвращает последнее известное состояние всех z2m устройств."""
    return JSONResponse(content=device_states)


@app.post("/api/entity/{entity_id:path}/command", dependencies=[Depends(verify_auth)])
async def post_command(entity_id: str, request: Request):
    """
    Принимает команду для устройства и пересылает в MQTT.
    entity_id = friendly_name устройства в z2m (может содержать пробелы, кодируется как %20).
    Body: {"state": "ON"} или {"state": "OFF"}
    """
    body = await request.json()
    state = body.get("state")
    if state not in ("ON", "OFF"):
        raise HTTPException(status_code=400, detail="state must be ON or OFF")
    await publish_command(entity_id, state)
    # Оптимистично обновляем in-memory состояние
    device_states[entity_id] = {"state": state}
    return JSONResponse(content={"ok": True})


# Монтируем фронтенд последним (чтобы не перехватывал /api/*)
# В продакшне static/ = собранный dist/
import os as _os
_static_path = _os.path.join(_os.path.dirname(__file__), "..", "static")
if _os.path.isdir(_static_path):
    app.mount("/", StaticFiles(directory=_static_path, html=True), name="static")
```

---

## Часть 2: Docker

### `Dockerfile`

Multi-stage: сначала собираем фронтенд Node.js, потом копируем в Python образ.

```dockerfile
# Stage 1: сборка фронтенда
FROM node:22-alpine AS frontend-build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Python сервер
FROM python:3.11-slim
WORKDIR /app

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/main.py .
COPY server/src/ ./src/

# Копируем собранный фронтенд в static/
COPY --from=frontend-build /app/dist ./static/

# Данные (конфиг) монтируются снаружи
VOLUME ["/data"]

CMD ["python", "main.py"]
```

### `.dockerignore` (добавить/обновить)

```
node_modules/
dist/
release/
.git/
.venv/
__pycache__/
*.pyc
```

### Запуск

```bash
docker build -t smarthome-floorplan .
docker run -p 8000:8000 \
  -v /path/to/data:/data \
  -e AUTH_PASSWORD=mysecret \
  -e MQTT_HOST=192.168.1.10 \
  -e MQTT_PORT=1883 \
  -e MQTT_USERNAME=user \
  -e MQTT_PASSWORD=pass \
  smarthome-floorplan
```

---

## Часть 3: Фронтенд — утилита API

### `src/utils/api.ts` (новый файл)

Все запросы к серверу идут через эти функции. Basic Auth строка хранится в `sessionStorage`.

```typescript
const SESSION_KEY = 'smarthome_auth';

export function getAuthHeader(): string {
    return sessionStorage.getItem(SESSION_KEY) ?? '';
}

export function setCredentials(username: string, password: string): void {
    const encoded = btoa(`${username}:${password}`);
    sessionStorage.setItem(SESSION_KEY, `Basic ${encoded}`);
}

export function clearCredentials(): void {
    sessionStorage.removeItem(SESSION_KEY);
}

async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
    const auth = getAuthHeader();
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(auth ? { Authorization: auth } : {}),
        ...(options.headers as Record<string, string> ?? {}),
    };
    const res = await fetch(path, { ...options, headers });
    if (res.status === 401) {
        clearCredentials();
        // Перезагружаем страницу чтобы показать форму логина
        window.location.reload();
    }
    return res;
}

export async function fetchConfig(): Promise<object> {
    const res = await apiFetch('/api/config');
    if (!res.ok) throw new Error('Failed to fetch config');
    return res.json();
}

export async function saveConfig(config: object): Promise<void> {
    const res = await apiFetch('/api/config', {
        method: 'POST',
        body: JSON.stringify(config),
    });
    if (!res.ok) throw new Error('Failed to save config');
}

export async function fetchStates(): Promise<Record<string, { state: string }>> {
    const res = await apiFetch('/api/states');
    if (!res.ok) throw new Error('Failed to fetch states');
    return res.json();
}

export async function sendCommand(entityId: string, state: 'ON' | 'OFF'): Promise<void> {
    const encodedId = encodeURIComponent(entityId);
    const res = await apiFetch(`/api/entity/${encodedId}/command`, {
        method: 'POST',
        body: JSON.stringify({ state }),
    });
    if (!res.ok) throw new Error('Failed to send command');
}

/**
 * Проверяет креды, делая тестовый запрос к /api/config.
 * Возвращает true если 200, false если 401.
 */
export async function checkCredentials(username: string, password: string): Promise<boolean> {
    const encoded = btoa(`${username}:${password}`);
    const res = await fetch('/api/config', {
        headers: { Authorization: `Basic ${encoded}` },
    });
    return res.status === 200;
}
```

---

## Часть 4: Фронтенд — компонент логина

### `src/components/LoginForm.vue` (новый файл)

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { checkCredentials, setCredentials } from '../utils/api';

const emit = defineEmits<{ (e: 'success'): void }>();

const password = ref('');
const error = ref('');
const loading = ref(false);

async function submit() {
    error.value = '';
    loading.value = true;
    try {
        const ok = await checkCredentials('admin', password.value);
        if (ok) {
            setCredentials('admin', password.value);
            emit('success');
        } else {
            error.value = 'Неверный пароль';
        }
    } catch (e) {
        error.value = 'Ошибка соединения с сервером';
    } finally {
        loading.value = false;
    }
}
</script>

<template>
    <div class="login-overlay">
        <div class="login-box">
            <h2>Smart Home Floorplan</h2>
            <form @submit.prevent="submit">
                <input
                    type="password"
                    v-model="password"
                    placeholder="Пароль"
                    autocomplete="current-password"
                    :disabled="loading"
                />
                <button type="submit" :disabled="loading || !password">
                    {{ loading ? '...' : 'Войти' }}
                </button>
                <p v-if="error" class="error">{{ error }}</p>
            </form>
        </div>
    </div>
</template>

<style scoped>
.login-overlay {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg-primary, #1a1a2e);
    z-index: 9999;
}
.login-box {
    background: var(--color-bg-secondary, #16213e);
    padding: 2rem;
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    min-width: 280px;
}
.login-box h2 { margin: 0; text-align: center; }
.login-box form { display: flex; flex-direction: column; gap: 0.75rem; }
.error { color: #ef4444; font-size: 0.85rem; margin: 0; }
</style>
```

---

## Часть 5: Фронтенд — App.vue

Полностью заменить `src/App.vue`. Добавляем:
- Состояние аутентификации
- Показ `LoginForm` пока не залогинен
- После логина: загружаем конфиг с сервера и состояния устройств
- Polling состояний каждые 5 секунд

```vue
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { RouterView } from 'vue-router';
import { useFloorplanStore } from './stores/floorplan';
import LoginForm from './components/LoginForm.vue';
import { getAuthHeader, fetchConfig, fetchStates } from './utils/api';
import type { FloorplanConfig } from './types/floorplan';
import { needsMigration, migrateConfig } from './utils/configMigration';

const store = useFloorplanStore();
const isAuthenticated = ref(false);
let pollInterval: ReturnType<typeof setInterval> | null = null;

async function initApp() {
    // Загружаем конфиг с сервера
    try {
        let config = await fetchConfig() as any;
        if (config.imageBase64) {
            config.imageBase64 = config.imageBase64.replace(/\s/g, '');
        }
        if (needsMigration(config)) {
            config = migrateConfig(config);
        }
        store.loadConfig(config as FloorplanConfig);
    } catch (e) {
        console.error('Failed to load config from server', e);
    }

    // Загружаем текущие состояния устройств
    await loadStates();

    // Polling состояний каждые 5 секунд
    pollInterval = setInterval(loadStates, 5000);
}

async function loadStates() {
    try {
        const states = await fetchStates();
        // states: { "Living Room Light": { state: "ON" }, ... }
        for (const [friendlyName, s] of Object.entries(states)) {
            store.setEntityState(friendlyName, s.state === 'ON' ? 'on' : 'off');
        }
    } catch (e) {
        console.error('Failed to load states', e);
    }
}

async function onLoginSuccess() {
    isAuthenticated.value = true;
    await initApp();
}

onMounted(async () => {
    // Если уже есть креды в sessionStorage — пробуем сразу
    if (getAuthHeader()) {
        try {
            await fetchConfig(); // проверка что 200
            isAuthenticated.value = true;
            await initApp();
        } catch {
            isAuthenticated.value = false;
        }
    }
});

onUnmounted(() => {
    if (pollInterval) clearInterval(pollInterval);
});
</script>

<template>
    <LoginForm v-if="!isAuthenticated" @success="onLoginSuccess" />
    <RouterView v-else />
</template>
```

---

## Часть 6: Фронтенд — store (floorplan.ts)

### Изменения в `src/stores/floorplan.ts`

1. Убрать `import defaultConfig from '../default_config'`
2. Инициализировать `config` пустым объектом (конфиг придёт с сервера)
3. Добавить debounced auto-save при изменении конфига
4. Добавить `toggleEntityState` → вызывает HTTP команду (смотри часть 7)

**Заменить начало файла** (импорты и инициализация store):

```typescript
import { defineStore } from 'pinia';
import { ref, computed, watch } from 'vue';
import type { FloorplanConfig, EntityConfig, EntityState } from '../types/floorplan';
import { v4 as uuidv4 } from 'uuid';
import { saveConfig, sendCommand } from '../utils/api';

// Убираем import defaultConfig — конфиг загружается с сервера через App.vue

export const useFloorplanStore = defineStore('floorplan', () => {
    const config = ref<FloorplanConfig>({
        id: uuidv4(),
        name: 'New Floorplan',
        imageBase64: '',
        entities: []
    });

    const selectedEntityId = ref<string | null>(null);
    const entityStates = ref<Record<string, EntityState>>({});

    const entities = computed(() => config.value.entities);
    const selectedEntity = computed(() =>
        config.value.entities.find(e => e.id === selectedEntityId.value)
    );

    // Auto-save с debounce 2 секунды
    let saveTimer: ReturnType<typeof setTimeout> | null = null;
    watch(config, () => {
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(() => {
            saveConfig(config.value).catch(e => console.error('Auto-save failed:', e));
        }, 2000);
    }, { deep: true });

    // ... (остальные функции без изменений: setBaseImage, addEntity, removeEntity, updateEntity, setEntityState, loadConfig, clearConfig)
```

**Изменить функцию `toggleEntityState`** — добавить вызов HTTP:

```typescript
async function toggleEntityState(entityId: string, entityType: string) {
    const current = entityStates.value[entityId] || { state: 'off' };
    let newStateStr: string;

    if (entityType === 'camera') {
        if (current.state === 'idle') newStateStr = 'streaming';
        else if (current.state === 'streaming') newStateStr = 'recording';
        else newStateStr = 'idle';
    } else {
        newStateStr = current.state === 'off' ? 'on' : 'off';
    }

    // Оптимистичное обновление локального состояния
    entityStates.value[entityId] = {
        state: newStateStr,
        shouldLightUp: newStateStr !== 'off' && newStateStr !== 'idle',
    };

    // Отправляем команду на сервер (только ON/OFF для z2m)
    if (entityType !== 'camera') {
        const mqttState = newStateStr === 'on' ? 'ON' : 'OFF';
        sendCommand(entityId, mqttState).catch(e =>
            console.error('Failed to send command:', e)
        );
    }
}
```

---

## Часть 7: Фронтенд — ViewerView.vue

В `src/views/ViewerView.vue` `toggleEntityState` уже используется правильно через store. Изменения в store (часть 6) автоматически добавят HTTP вызов. Никаких изменений в ViewerView не требуется.

---

## Часть 8: Фронтенд — PropertiesPanel.vue

Убрать кнопки "Export YAML" и "Import YAML" из `src/components/editor/PropertiesPanel.vue`, так как конфиг теперь автоматически сохраняется на сервер.

**Найти и удалить** в шаблоне:
```html
<div class="io-actions">
    <button class="secondary" @click="clearAll" style="color: var(--color-danger)">Clear All</button>
    <button class="secondary" @click="exportConfigYaml">Export YAML</button>
    <button class="secondary" @click="triggerImport">Import YAML</button>
    <input ref="importInput" type="file" accept=".yaml,.yml" class="hidden-input" @change="onImportFile">
</div>
```

**Заменить на** (оставить только Clear All):
```html
<div class="io-actions">
    <button class="secondary" @click="clearAll" style="color: var(--color-danger)">Clear All</button>
</div>
```

**Удалить из `<script setup>`** функции: `exportConfigYaml`, `downloadString`, `triggerImport`, `onImportFile` и ref `importInput`.

---

## Часть 9: Фронтенд — vite.config.ts

Добавить proxy для dev-режима, чтобы `/api` запросы шли на локальный Python сервер.

**Заменить** `vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { execSync } from 'child_process';

const commitHash = execSync('git describe --tags --always').toString().trim();

export default defineConfig({
  base: './',
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify(commitHash)
  },
  build: {
    sourcemap: true
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
```

---

## Итоговая структура проекта

```
smarthome_floorplan/
├── Dockerfile
├── .dockerignore
├── package.json
├── vite.config.ts              ← изменён (добавлен proxy)
├── src/
│   ├── App.vue                 ← изменён (auth + init)
│   ├── utils/
│   │   ├── api.ts              ← НОВЫЙ
│   │   └── configMigration.ts
│   ├── components/
│   │   ├── LoginForm.vue       ← НОВЫЙ
│   │   ├── common/
│   │   └── editor/
│   │       └── PropertiesPanel.vue  ← изменён (убраны export/import)
│   ├── stores/
│   │   └── floorplan.ts        ← изменён (auto-save, HTTP команды)
│   └── views/
│       └── ViewerView.vue      ← без изменений
└── server/
    ├── main.py                 ← НОВЫЙ
    ├── requirements.txt        ← НОВЫЙ
    └── src/
        ├── __init__.py         ← НОВЫЙ
        ├── api.py              ← НОВЫЙ
        ├── config_store.py     ← НОВЫЙ
        └── mqtt_client.py      ← НОВЫЙ
```

---

## Порядок реализации для кодера

1. **Создать `server/`** — `requirements.txt`, `main.py`, `src/__init__.py`, `src/config_store.py`, `src/mqtt_client.py`, `src/api.py`
2. **Создать `src/utils/api.ts`**
3. **Создать `src/components/LoginForm.vue`**
4. **Изменить `src/App.vue`** — убрать старое содержимое, вставить новое
5. **Изменить `src/stores/floorplan.ts`** — убрать default_config, добавить auto-save и HTTP команды
6. **Изменить `src/components/editor/PropertiesPanel.vue`** — убрать export/import кнопки и функции
7. **Изменить `vite.config.ts`** — добавить proxy
8. **Создать `Dockerfile` и обновить `.dockerignore`**
9. **Тест**: запустить Python сервер (`cd server && python main.py`), запустить фронтенд (`npm run dev`)

---

## Замечания

- **`entityId`** в конфиге — это `friendly_name` из z2m. Нужно объяснить пользователям что имена устройств на плане должны точно совпадать с именами в z2m.
- **Polling** состояний каждые 5 секунд — простейшее решение. В будущем можно заменить на WebSocket/SSE.
- **Camera** тип устройств не отправляет MQTT команды (z2m не управляет камерами таким образом) — в `toggleEntityState` команда отправляется только для не-camera типов.
- **`AUTH_PASSWORD`** в env — обязательный параметр. При отсутствии не запускаем сервер.
