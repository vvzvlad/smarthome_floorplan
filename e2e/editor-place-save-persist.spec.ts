import { test, expect } from '@playwright/test'
import { installBackend, makeState, IMG_DATA_URI } from './fixtures'

// Journey 2: editor -> add an entity -> debounced auto-save -> reload restores it.
// Image upload is awkward to mock, so we seed a base image and focus on the
// add -> persist -> reload-restore loop. The store auto-saves with a 2s debounce;
// we wait for the resulting POST /api/config and assert the new entity is in the body.
// Our mock persists that body, so the post-reload GET /api/config restores it.
test('add an entity in the editor, auto-save persists it, and reload restores it', async ({ page }) => {
    const state = makeState({
        auth: true,
        config: {
            id: 'cfg-e2e',
            name: 'E2E Plan',
            imageBase64: IMG_DATA_URI,
            entities: [],
        },
    })
    await installBackend(page, state)

    // Authed: go straight to the editor (hash route).
    await page.goto('/#/editor')
    await expect(page.locator('header.app-header')).toBeVisible()

    // With no selection the panel shows the Add buttons.
    const addLight = page.getByRole('button', { name: 'Add Light Entity' })
    await expect(addLight).toBeVisible()

    // Wait for the debounced auto-save triggered by adding the entity (2s debounce).
    const [saveRequest] = await Promise.all([
        page.waitForRequest(
            (r) => r.url().includes('/api/config') && r.method() === 'POST',
            { timeout: 10000 },
        ),
        addLight.click(),
    ])

    // The editor reflects the new entity: it is now selected, so the entity
    // properties panel (with the Entity ID field) is shown.
    await expect(page.locator('.entity-properties')).toBeVisible()
    await expect(page.getByPlaceholder('z2m friendly_name')).toBeVisible()

    // The saved body carries exactly one entity of type "light".
    const savedBody = saveRequest.postDataJSON() as { entities: Array<{ type: string }> }
    expect(savedBody.entities).toHaveLength(1)
    expect(savedBody.entities[0].type).toBe('light')

    // The mock persisted that body. Reload: GET /api/config returns it -> entity restored.
    await page.reload()
    await expect(page.locator('header.app-header')).toBeVisible()

    // Re-navigate to the editor and confirm the entity survived (the canvas
    // renders one EntityOverlay element per entity).
    await page.goto('/#/editor')
    await expect(page.locator('.entity-overlay')).toHaveCount(1, { timeout: 10000 })

    // And the persisted config still has the entity from the server's perspective.
    expect((state.config as { entities: unknown[] }).entities).toHaveLength(1)
})
