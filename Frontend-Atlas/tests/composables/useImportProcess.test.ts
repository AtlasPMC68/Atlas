import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useImportProcess } from '../../src/composables/useImportProcess'

vi.stubGlobal('fetch', vi.fn())

describe('useImportProcess', () => {
  let composable: ReturnType<typeof useImportProcess>

  beforeEach(() => {
    composable = useImportProcess()
    vi.clearAllMocks()
  })

  it('should return error if no file is provided', async () => {
    const result = await composable.startImport(null as any)
    expect(result.success).toBe(false)
    expect(result.error).toBe('Aucun fichier sélectionné')
  })

  it('should handle file upload and start polling on success', async () => {
    vi.useFakeTimers()

    const fakeFile = new File(['dummy content'], 'test.csv', { type: 'text/csv' })
    const mockTaskId = '12345'

    ;(fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ task_id: mockTaskId }),
    })

    ;(fetch as any).mockResolvedValueOnce({
      json: async () => ({
        state: 'SUCCESS',
        progress_percentage: 100,
        status: 'Done',
        result: { message: 'Success' },
      }),
    })

    const result = await composable.startImport(fakeFile)

    await vi.advanceTimersByTimeAsync(1000)

    expect(result.success).toBe(true)
    expect(composable.isProcessing.value).toBe(false)
    expect(composable.resultData.value).toEqual({ message: 'Success' })

    vi.useRealTimers()
  })

  it('should return error on failed upload', async () => {
    ;(fetch as any).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Fichier invalide' }),
    })

    const fakeFile = new File(['dummy'], 'invalid.csv')

    const result = await composable.startImport(fakeFile)
    expect(result.success).toBe(false)
    expect(result.error).toBe('Fichier invalide')
    expect(composable.isProcessing.value).toBe(false)
  })

  it('should cancel import correctly', () => {
    composable.isProcessing.value = true
    composable.processingStep.value = 'extraction'
    composable.processingProgress.value = 50

    composable.cancelImport()

    expect(composable.isProcessing.value).toBe(false)
    expect(composable.processingStep.value).toBe('upload')
    expect(composable.processingProgress.value).toBe(0)
    expect(composable.resultData.value).toBeNull()
  })
})
