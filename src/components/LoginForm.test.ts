import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Mock the api module so `login` is a controllable spy. Path is relative to the
// component under test (src/components/LoginForm.vue imports '../utils/api').
vi.mock('../utils/api', () => ({
    login: vi.fn(),
}))

import LoginForm from './LoginForm.vue'
import * as api from '../utils/api'

const loginMock = vi.mocked(api.login)

beforeEach(() => {
    loginMock.mockReset()
})

describe('LoginForm', () => {
    it('emits "success" and shows no error when login resolves true', async () => {
        loginMock.mockResolvedValue(true)
        const wrapper = mount(LoginForm)

        await wrapper.find('input[type="password"]').setValue('correct-password')
        await wrapper.find('form').trigger('submit')
        await flushPromises()

        // login was called with the typed password.
        expect(loginMock).toHaveBeenCalledTimes(1)
        expect(loginMock).toHaveBeenCalledWith('correct-password')
        // success emitted exactly once, no error rendered.
        expect(wrapper.emitted('success')).toHaveLength(1)
        expect(wrapper.find('.error').exists()).toBe(false)
    })

    it('shows "Wrong password" and does NOT emit success when login resolves false', async () => {
        loginMock.mockResolvedValue(false)
        const wrapper = mount(LoginForm)

        await wrapper.find('input[type="password"]').setValue('bad')
        await wrapper.find('form').trigger('submit')
        await flushPromises()

        expect(wrapper.find('.error').text()).toBe('Wrong password')
        expect(wrapper.emitted('success')).toBeUndefined()
    })

    it('shows the connection-error text when login throws', async () => {
        loginMock.mockRejectedValue(new Error('network down'))
        const wrapper = mount(LoginForm)

        await wrapper.find('input[type="password"]').setValue('whatever')
        await wrapper.find('form').trigger('submit')
        await flushPromises()

        expect(wrapper.find('.error').text()).toBe('Cannot connect to server')
        expect(wrapper.emitted('success')).toBeUndefined()
    })

    it('disables the submit button and input while the request is pending, then re-enables', async () => {
        // Hold the login promise open so we can observe the pending state.
        let resolveLogin!: (v: boolean) => void
        loginMock.mockImplementation(() => new Promise<boolean>((r) => { resolveLogin = r }))

        const wrapper = mount(LoginForm)
        const input = wrapper.find('input[type="password"]')
        await input.setValue('correct')
        await wrapper.find('form').trigger('submit')
        // microtask: loading flipped true synchronously before await.
        await wrapper.vm.$nextTick()

        const button = wrapper.find('button[type="submit"]')
        expect((button.element as HTMLButtonElement).disabled).toBe(true)
        expect((input.element as HTMLInputElement).disabled).toBe(true)
        expect(button.text()).toBe('...')

        // Resolve and let the finally-block clear loading.
        resolveLogin(true)
        await flushPromises()
        expect(wrapper.emitted('success')).toHaveLength(1)
    })

    it('keeps the submit button disabled while the password is empty', async () => {
        loginMock.mockResolvedValue(true)
        const wrapper = mount(LoginForm)

        const button = wrapper.find('button[type="submit"]')
        // Empty password -> button disabled (`:disabled="loading || !password"`).
        expect((button.element as HTMLButtonElement).disabled).toBe(true)

        await wrapper.find('input[type="password"]').setValue('x')
        expect((button.element as HTMLButtonElement).disabled).toBe(false)
    })

    it('does not double-submit: a single submit triggers exactly one login call', async () => {
        let resolveLogin!: (v: boolean) => void
        loginMock.mockImplementation(() => new Promise<boolean>((r) => { resolveLogin = r }))

        const wrapper = mount(LoginForm)
        await wrapper.find('input[type="password"]').setValue('pw')
        // Two rapid submits; the button is disabled while pending so the second is a no-op.
        await wrapper.find('form').trigger('submit')
        await wrapper.find('button[type="submit"]').trigger('click')
        await wrapper.vm.$nextTick()

        expect(loginMock).toHaveBeenCalledTimes(1)
        resolveLogin(true)
        await flushPromises()
    })
})
