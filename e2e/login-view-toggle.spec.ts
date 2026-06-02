import { test, expect } from '@playwright/test'
import { installBackend, makeState, lightEntity, IMG_DATA_URI } from './fixtures'

// Journey 1: login -> viewer -> toggle a device.
// Starts unauthenticated (session=false) so the login form shows; submitting the
// password flips the mocked session to authed and the app reveals the viewer with
// one light entity. Clicking the entity must fire POST /api/entity/<id>/command
// with the expected { state } body.
test('login, view the floorplan, and toggle a light device', async ({ page }) => {
    const state = makeState({
        auth: false,
        title: 'My House',
        config: {
            id: 'cfg-e2e',
            name: 'E2E Plan',
            imageBase64: IMG_DATA_URI,
            entities: [lightEntity()],
        },
        states: { 'light.living_room': { state: 'off' } },
    })
    await installBackend(page, state)

    await page.goto('/')

    // Unauthenticated -> login form is visible, no app header.
    const password = page.getByPlaceholder('Password')
    await expect(password).toBeVisible()
    await expect(page.locator('header.app-header')).toHaveCount(0)

    // Submit the password; the mock flips session -> authed and returns ok.
    await password.fill('secret')
    await page.getByRole('button', { name: 'Login' }).click()

    // App revealed: header with the fetched title, login gone.
    await expect(page.locator('header.app-header')).toBeVisible()
    await expect(page.locator('.login-overlay')).toHaveCount(0)
    await expect(page.locator('header .logo')).toHaveText('My House')

    // The single light entity renders in the viewer.
    const entity = page.locator('.interactive-entity').first()
    await expect(entity).toBeVisible()

    // Click toggles it ON: assert the command request body.
    const [request] = await Promise.all([
        page.waitForRequest(
            (r) => r.url().includes('/api/entity/') && r.url().includes('/command') && r.method() === 'POST',
        ),
        entity.click(),
    ])
    expect(request.postDataJSON()).toEqual({ state: 'ON' })
    // It targeted the correct entity id (URL-encoded in the path).
    expect(decodeURIComponent(new URL(request.url()).pathname)).toContain('/api/entity/light.living_room/command')
})
