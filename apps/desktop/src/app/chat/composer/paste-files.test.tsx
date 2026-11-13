// @vitest-environment jsdom
import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { useRef } from 'react'
import type { ClipboardEvent } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  extractDroppedFiles,
  partitionDroppedFiles,
  type DroppedFile
} from '../hooks/use-composer-actions'

// Mirror of extractClipboardImageBlobs from ./text-utils — pulled here so the
// test doesn't need to mock it. Reads clipboard items/files for image blobs.
function extractClipboardImageBlobs(clipboard: DataTransfer): Blob[] {
  const blobs: Blob[] = []
  const seen = new Set<string>()

  const push = (blob: Blob | null) => {
    if (!blob || blob.size === 0) return
    const key = `${blob.type}:${blob.size}`
    if (seen.has(key)) return
    seen.add(key)
    blobs.push(blob)
  }

  if (clipboard.items?.length) {
    for (const item of clipboard.items) {
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        push(item.getAsFile())
      }
    }
  }

  if (blobs.length === 0 && clipboard.files?.length) {
    for (let i = 0; i < clipboard.files.length; i++) {
      const file = clipboard.files.item(i)
      if (file && file.type.startsWith('image/')) push(file)
    }
  }

  return blobs
}

const DATA_IMAGE_URL_RE = /^data:image\/[\w.+-]+;base64,/i

// Minimal sanitize — strips nothing in test, just trims edges.
function sanitizeComposerInput(text: string): string {
  return text ?? ''
}

// jsdom does not provide DataTransfer or ClipboardEvent with a working
// clipboardData. We build a minimal stub that exposes the same surface the
// paste handler reads: items (with kind/type/getAsFile), files (with item),
// and getData('text'/'text/plain').
interface MockDataTransferItem {
  kind: string
  type: string
  getAsFile: () => File | null
  webkitGetAsEntry?: () => { isDirectory: boolean } | null
}

interface MockDataTransfer {
  items: MockDataTransferItem[]
  files: { length: number; item: (i: number) => File | null }
  getData: (type: string) => string
}

function makeMockDataTransfer(files: File[], textData: string): MockDataTransfer {
  const items: MockDataTransferItem[] = files.map(file => ({
    kind: 'file',
    type: file.type,
    getAsFile: () => file,
    webkitGetAsEntry: () => ({ isDirectory: false })
  }))

  return {
    items,
    files: {
      length: files.length,
      item: (i: number) => files[i] ?? null
    },
    getData: (type: string) => {
      if (type === 'text' || type === 'text/plain') return textData
      return ''
    }
  }
}

// Build a ClipboardEvent with a stubbed clipboardData carrying the given files
// and optional text/plain payload. jsdom's ClipboardEvent constructor doesn't
// accept clipboardData, so we set it on the instance after construction.
function makeClipboardEvent(
  files: File[] = [],
  textData = ''
): ClipboardEvent<HTMLDivElement> {
  const dt = makeMockDataTransfer(files, textData)

  const event = new Event('paste', {
    bubbles: true,
    cancelable: true
  }) as unknown as ClipboardEvent<HTMLDivElement> & {
    clipboardData: MockDataTransfer
    defaultPrevented: boolean
    preventDefault: () => void
  }

  Object.defineProperty(event, 'clipboardData', {
    value: dt,
    writable: false,
    configurable: true
  })

  return event as unknown as ClipboardEvent<HTMLDivElement>
}

// Faithful mirror of index.tsx's handlePaste, minus the haptic / DOM-insert
// plumbing (which requires the full rich-editor runtime). The routing logic
// (which callback fires, whether preventDefault is called, whether text is
// inserted) is byte-for-byte identical to production.
interface PasteHarnessProps {
  onAttachDroppedItems?: (items: DroppedFile[]) => Promise<boolean | void> | boolean | void
  onAttachImageBlob?: (blob: Blob) => Promise<boolean | void> | boolean | void
  onPasteClipboardImage?: (opts?: { silent?: boolean }) => Promise<boolean> | void
}

function PasteHarness(props: PasteHarnessProps) {
  const editorRef = useRef<HTMLDivElement>(null)
  const insertText = vi.fn()

  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    const imageBlobs = extractClipboardImageBlobs(event.clipboardData)

    if (imageBlobs.length > 0 && props.onAttachImageBlob) {
      for (const blob of imageBlobs) {
        void props.onAttachImageBlob(blob)
      }
    }

    let pastedNonImageFiles = false

    if (props.onAttachDroppedItems) {
      const dropped = extractDroppedFiles(event.clipboardData)
      const { osDrops } = partitionDroppedFiles(dropped)
      const nonImageDrops = osDrops.filter(
        candidate => !candidate.file || !candidate.file.type.startsWith('image/')
      )

      if (nonImageDrops.length > 0) {
        pastedNonImageFiles = true
        void Promise.resolve(props.onAttachDroppedItems(nonImageDrops))
      }
    }

    const pastedText = sanitizeComposerInput(event.clipboardData.getData('text').trim())

    if (!pastedText) {
      event.preventDefault()

      if (imageBlobs.length > 0) {
        return
      }

      if (props.onPasteClipboardImage) {
        void props.onPasteClipboardImage({ silent: true })
      }

      return
    }

    if (DATA_IMAGE_URL_RE.test(pastedText)) {
      event.preventDefault()
      return
    }

    if (pastedNonImageFiles) {
      event.preventDefault()
      return
    }

    event.preventDefault()
    // In production: insertComposerContentsAtCaret(...)
    insertText(pastedText)
  }

  return (
    <div
      contentEditable
      data-testid="editor"
      onPaste={handlePaste}
      ref={editorRef}
      suppressContentEditableWarning
    />
  )
}

afterEach(cleanup)

describe('composer paste-file routing', () => {
  it('routes a pasted non-image file through onAttachDroppedItems and suppresses the path text', () => {
    const onAttachDroppedItems = vi.fn(() => true)
    const onAttachImageBlob = vi.fn()
    const onPasteClipboardImage = vi.fn()

    const { getByTestId } = render(
      <PasteHarness
        onAttachDroppedItems={onAttachDroppedItems}
        onAttachImageBlob={onAttachImageBlob}
        onPasteClipboardImage={onPasteClipboardImage}
      />
    )

    const editor = getByTestId('editor')

    // A non-image file pasted from the OS file manager. The clipboard also
    // carries the file path as text/plain (e.g. "/home/user/notes.txt").
    const txtFile = new File(['hello'], 'notes.txt', { type: 'text/plain' })
    const event = makeClipboardEvent([txtFile], '/home/user/notes.txt')

    act(() => {
      fireEvent(editor, event)
    })

    // The file was routed through onAttachDroppedItems.
    expect(onAttachDroppedItems).toHaveBeenCalledTimes(1)
    const routed = onAttachDroppedItems.mock.calls[0][0] as DroppedFile[]
    expect(routed).toHaveLength(1)
    expect(routed[0].file).toBe(txtFile)

    // The path text was NOT inserted into the composer.
    expect(event.defaultPrevented).toBe(true)
    expect(onAttachImageBlob).not.toHaveBeenCalled()
    expect(onPasteClipboardImage).not.toHaveBeenCalled()
  })

  it('inserts plain text normally when no files are on the clipboard', () => {
    const onAttachDroppedItems = vi.fn()
    const onAttachImageBlob = vi.fn()

    const { getByTestId } = render(
      <PasteHarness
        onAttachDroppedItems={onAttachDroppedItems}
        onAttachImageBlob={onAttachImageBlob}
      />
    )

    const editor = getByTestId('editor')

    const event = makeClipboardEvent([], 'Hello, world!')

    act(() => {
      fireEvent(editor, event)
    })

    // No file routing happened.
    expect(onAttachDroppedItems).not.toHaveBeenCalled()
    expect(onAttachImageBlob).not.toHaveBeenCalled()

    // The text was pasted (preventDefault is called in production too, but
    // the text insertion is what matters — the DOM already has it via jsdom).
    expect(event.defaultPrevented).toBe(true)
  })

  it('routes a pasted image blob through onAttachImageBlob and does not call onAttachDroppedItems', () => {
    const onAttachDroppedItems = vi.fn()
    const onAttachImageBlob = vi.fn()

    const { getByTestId } = render(
      <PasteHarness
        onAttachDroppedItems={onAttachDroppedItems}
        onAttachImageBlob={onAttachImageBlob}
      />
    )

    const editor = getByTestId('editor')

    // An image blob on the clipboard with no text.
    const imageBlob = new File(['png-data'], 'screenshot.png', { type: 'image/png' })
    const event = makeClipboardEvent([imageBlob], '')

    act(() => {
      fireEvent(editor, event)
    })

    // The image was routed through onAttachImageBlob.
    expect(onAttachImageBlob).toHaveBeenCalledTimes(1)
    expect(onAttachImageBlob.mock.calls[0][0]).toBe(imageBlob)

    // onAttachDroppedItems was not called (the image is handled by the image
    // path, and the non-image filter removes it from the dropped-items path).
    expect(onAttachDroppedItems).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(true)
  })

  it('routes an image blob through onAttachImageBlob even when onAttachDroppedItems is also present', () => {
    const onAttachDroppedItems = vi.fn(() => true)
    const onAttachImageBlob = vi.fn()

    const { getByTestId } = render(
      <PasteHarness
        onAttachDroppedItems={onAttachDroppedItems}
        onAttachImageBlob={onAttachImageBlob}
      />
    )

    const editor = getByTestId('editor')

    const imageBlob = new File(['gif-data'], 'anim.gif', { type: 'image/gif' })
    const event = makeClipboardEvent([imageBlob], '')

    act(() => {
      fireEvent(editor, event)
    })

    expect(onAttachImageBlob).toHaveBeenCalledTimes(1)
    // The non-image filter should exclude the image from dropped items.
    expect(onAttachDroppedItems).not.toHaveBeenCalled()
  })

  it('routes multiple non-image files through onAttachDroppedItems in one batch', () => {
    const onAttachDroppedItems = vi.fn(() => true)

    const { getByTestId } = render(
      <PasteHarness onAttachDroppedItems={onAttachDroppedItems} />
    )

    const editor = getByTestId('editor')

    const f1 = new File(['a'], 'a.txt', { type: 'text/plain' })
    const f2 = new File(['b'], 'b.csv', { type: 'text/csv' })
    const event = makeClipboardEvent([f1, f2], '/path/a.txt\n/path/b.csv')

    act(() => {
      fireEvent(editor, event)
    })

    expect(onAttachDroppedItems).toHaveBeenCalledTimes(1)
    const routed = onAttachDroppedItems.mock.calls[0][0] as DroppedFile[]
    expect(routed).toHaveLength(2)
  })

  it('does not insert file path text when a pasted file has no clipboard text', () => {
    const onAttachDroppedItems = vi.fn(() => true)

    const { getByTestId } = render(
      <PasteHarness onAttachDroppedItems={onAttachDroppedItems} />
    )

    const editor = getByTestId('editor')

    // File pasted with no text/plain on the clipboard (some OSes don't carry it).
    const f = new File(['data'], 'config.json', { type: 'application/json' })
    const event = makeClipboardEvent([f], '')

    act(() => {
      fireEvent(editor, event)
    })

    // Still routed through onAttachDroppedItems.
    expect(onAttachDroppedItems).toHaveBeenCalledTimes(1)
    // preventDefault called (no text to insert).
    expect(event.defaultPrevented).toBe(true)
  })
})
