import { test, expect } from '@playwright/test'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mockBackend, seedApiKey } from '../harness'
const fixtures = join(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures')

for (const [outcome, tone, label] of [
  ['max_rounds_reached', 'warning', 'Max rounds'],
  ['verdict_pass', 'success', 'Accepted'],
  ['verdict_fail', 'danger', 'Not accepted'],
]) {
  test(`meeting ${outcome} displays its actual outcome and bounded ended round`, async ({ page }) => {
    await seedApiKey(page)
    await mockBackend(page, [join(fixtures, '_app_boot_noise.yaml')])
    const meeting = { meeting_id: 'retro-proof', agenda: 'Checkpoint retrospective', participants: ['PM', 'QE'], started: true, ended: true, outcome, current_round: 3, max_rounds: 2 }
    await page.route('**/api/agent/meetings', r => r.fulfill({ json: { meetings: [meeting] } }))
    await page.route('**/api/agent/meetings/retro-proof/stream**', r => r.fulfill({
      headers: { 'content-type': 'text/event-stream' },
      body: 'retry: 3600000\n\ndata: ' + JSON.stringify({ type: 'state_changed', data: { state: meeting } }) + '\n\n',
    }))
    await page.goto('/meetings?id=retro-proof')
    const badge = page.locator('.tp-pill.ended-pill')
    await expect(badge).toHaveClass(new RegExp(tone))
    await expect(badge).toContainText(label)
    await expect(page.locator('.tp-meta')).toContainText('2 / 2')
    if (tone !== 'success') await expect(badge).not.toContainText('✓')
  })
}
