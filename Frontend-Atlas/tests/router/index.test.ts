import { describe, it, expect, beforeEach } from 'vitest'
import { router } from '../../src/router'

const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => (store[key] = value),
    removeItem: (key: string) => delete store[key],
    clear: () => (store = {})
  }
})()

Object.defineProperty(window, 'localStorage', { value: localStorageMock })

describe('router auth guard integration', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('redirects to /connexion if not authenticated and route requires auth', async () => {
    localStorage.removeItem('access_token')

    try {
      await router.push('/demo/upload')
    } catch (e) {
    }

    expect(router.currentRoute.value.fullPath).toBe('/connexion')
  })

  it('does not allows access if access_token is wrong', async () => {
    localStorage.setItem('access_token', 'token123')

    await router.push('/demo/upload')
    expect(router.currentRoute.value.fullPath).toBe('/connexion')
  })

  it('allows access to unprotected route', async () => {
    localStorage.removeItem('access_token')

    await router.push('/inscription')
    expect(router.currentRoute.value.fullPath).toBe('/inscription')
  })
})
