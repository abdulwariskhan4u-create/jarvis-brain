import { test, expect } from '@playwright/test'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mockBackend, seedApiKey } from '../harness'

const fixtures = join(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures')

async function setup(page, repairSucceeds: boolean) {
  await seedApiKey(page)
  await mockBackend(page, [join(fixtures, '_app_boot_noise.yaml')])
  let repaired = false
  let repairs = 0
  await page.route('**/api/memory/settings', route => route.fulfill({ json: {
    enabled: true, mode: 'balanced', approval_policy: 'manual', graph_max_hops: 1,
  } }))
  await page.route('**/api/memory/index-status', route => route.fulfill({ json: {
    enabled: true, outbox: { pending: 0 },
    dense: { reachable: true, embeddings: true, points: 9, searchable: repaired, broken: !repaired },
  } }))
  await page.route('**/api/memory/repair', route => {
    repairs++
    repaired = repairSucceeds
    return route.fulfill({ json: { status: repaired ? 'ok' : 'degraded', index_rebuilt: repaired } })
  })
  await page.goto('/settings')
  await page.getByRole('button', { name: 'Agent Memory', exact: true }).click()
  return () => repairs
}

test('reachable but unsearchable index warns; successful restore updates health', async ({ page }) => {
  const repairs = await setup(page, true)
  await expect(page.getByRole('alert')).toContainText('Semantic memory is DOWN')
  await expect(page.locator('.status-card').getByText('Connected', { exact: false })).not.toBeVisible()
  await page.getByRole('button', { name: 'Restore index' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.locator('.status-card').getByText('Connected ·')).toBeVisible()
  expect(repairs()).toBe(1)
})

test('failed native repair keeps warning and permits retry', async ({ page }) => {
  const repairs = await setup(page, false)
  await page.getByRole('button', { name: 'Restore index' }).click()
  await expect(page.getByRole('alert')).toContainText('Semantic memory is DOWN')
  await expect(page.getByRole('button', { name: 'Restore index' })).toBeEnabled()
  await expect(page.locator('.error')).toContainText('Semantic memory is DOWN')
  expect(repairs()).toBe(1)
})
