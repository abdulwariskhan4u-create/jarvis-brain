import { test } from 'node:test'
import assert from 'node:assert/strict'
import { useChatStream } from './useChatStream.js'

test('HTTP failure exposes the error message consumed by both chat UIs', async () => {
  const previous = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({detail:'Backend is still starting up'}), {status:503})
    const stream = useChatStream()
    const events = []
    await stream.send('Continue', null, event => events.push(event))
    assert.equal(events.length, 1)
    assert.equal(events[0].type, 'error')
    assert.match(events[0].message, /503.*Backend is still starting up/)
    assert.equal(stream.isStreaming.value, false)
    assert.equal(stream.lastError.value, events[0].message)
  } finally { globalThis.fetch = previous }
})
