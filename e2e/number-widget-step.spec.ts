import { test, expect } from '@playwright/test'
import { installBackend, makeState, numberEntity, IMG_DATA_URI } from './fixtures'

// Journey 3: number stepper publishes the correct raw topic/value.
// The viewer's stepper "+" routes through store.setNumberValue -> publishRaw,
// which is POST /api/mqtt/publish with body { topic, value }. With no read-topic
// value the widget resolves to min (0); stepping by 5 must publish "5" to the
// configured write topic.
test('stepping the number widget publishes the correct topic and value', async ({ page }) => {
    const state = makeState({
        auth: true,
        config: {
            id: 'cfg-e2e',
            name: 'E2E Plan',
            imageBase64: IMG_DATA_URI,
            entities: [numberEntity()],
        },
        states: {},
        topics: {},
    })
    await installBackend(page, state)

    await page.goto('/')
    await expect(page.locator('header.app-header')).toBeVisible()

    // The stepper renders: "−", value, "+".
    const stepper = page.locator('.number-stepper').first()
    await expect(stepper).toBeVisible()
    const plus = stepper.getByRole('button', { name: '+' })

    // Click "+" -> publish min+step (0 + 5 = 5) to the write topic.
    const [request] = await Promise.all([
        page.waitForRequest((r) => r.url().includes('/api/mqtt/publish') && r.method() === 'POST'),
        plus.click(),
    ])

    expect(request.postDataJSON()).toEqual({ topic: 'home/room/setpoint/set', value: '5' })
})
