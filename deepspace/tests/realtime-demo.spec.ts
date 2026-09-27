/**
 * Two signed-in sessions share one record room. A confirmed responder
 * mutation in the first session must show up in the second without a reload.
 */
import { test, expect, loadAllTestAccounts } from 'deepspace/testing'

const usableTestAccounts = loadAllTestAccounts().length
test.skip(
  usableTestAccounts < 2,
  `Needs 2 usable test accounts, found ${usableTestAccounts}. Create them with ` +
    '`npx deepspace test accounts create --email <name>@deepspace.test --name "<name>" ' +
    '--password-stdin`.',
)

test.describe.configure({ mode: 'serial' })

async function resetDemoIncidentIfPresent(page: import('@playwright/test').Page) {
  const reset = page.getByTestId('reset-test-incident')
  if (await reset.isVisible().catch(() => false)) {
    await reset.click()
    await expect(page.getByTestId('incidents-empty')).toBeVisible({ timeout: 15_000 })
  }
}

test('responder status syncs across signed-in sessions', async ({ users }) => {
  const [a, b] = await users(2)
  await Promise.all([a.page.goto('/home'), b.page.goto('/home')])
  await resetDemoIncidentIfPresent(a.page)

  await expect(a.page.getByTestId('camera-count')).toHaveText('10', { timeout: 20_000 })
  await expect(b.page.getByTestId('camera-count')).toHaveText('10', { timeout: 20_000 })
  await expect(a.page.getByTestId('active-incident-count')).toHaveText('0')
  await expect(a.page.getByTestId('incidents-empty')).toHaveText('No active incidents')

  const statusA = a.page.getByTestId('responder-status-UNIT-12')
  const statusB = b.page.getByTestId('responder-status-UNIT-12')
  const initial = (await statusA.textContent())?.trim()
  expect(initial === 'available' || initial === 'unavailable').toBe(true)
  const next = initial === 'available' ? 'unavailable' : 'available'

  await a.page.getByTestId('toggle-status-UNIT-12').click()
  await expect(statusA).toHaveText(next, { timeout: 10_000 })
  await expect(statusB).toHaveText(next, { timeout: 10_000 })

  const availableB = Number(await b.page.getByTestId('available-responder-count').textContent())
  expect(Number.isInteger(availableB)).toBe(true)

  await a.page.getByTestId('toggle-status-UNIT-12').click()
  await expect(statusB).toHaveText(initial!, { timeout: 10_000 })
})

test('assignment appears on the responder page and status changes sync back', async ({ users }) => {
  test.setTimeout(90_000)
  const [home, responder] = await users(2)
  await home.page.goto('/home')
  await responder.page.goto('/responder/UNIT-42')

  try {
    await resetDemoIncidentIfPresent(home.page)
    await expect(home.page.getByTestId('responder-status-UNIT-42')).toHaveText('available', { timeout: 20_000 })
    await expect(responder.page.getByTestId('responder-current-status')).toHaveText('available', { timeout: 20_000 })
    await expect(responder.page.getByTestId('no-active-assignment')).toBeVisible()

    await home.page.getByTestId('create-test-incident').click()
    await expect(home.page.getByTestId('test-incident-label')).toHaveText('TEST / DEMO INCIDENT', { timeout: 15_000 })
    await expect(home.page.getByTestId('test-incident-camera')).toHaveText('CAM-007')
    await expect(home.page.getByTestId('test-incident-status')).toHaveText('open')

    await home.page.getByTestId('assign-nearest').click()
    await expect(home.page.getByTestId('test-incident-assignee')).toHaveText('Assigned: UNIT-42', { timeout: 15_000 })
    await expect(home.page.getByTestId('test-incident-status')).toHaveText('assigned')
    await expect(home.page.getByTestId('test-incident-distance')).toHaveText('Distance: 0.00 km')

    await expect(responder.page.getByRole('heading', { name: 'POSSIBLE COLLISION' })).toBeVisible({ timeout: 15_000 })
    await responder.page.getByTestId('accept-assignment').click()
    await expect(home.page.getByTestId('test-incident-status')).toHaveText('accepted', { timeout: 15_000 })

    await responder.page.getByTestId('en-route').click()
    await expect(home.page.getByTestId('test-incident-status')).toHaveText('responding', { timeout: 15_000 })

    await responder.page.getByTestId('on-scene').click()
    await expect(home.page.getByTestId('test-incident-status')).toHaveText('on_scene', { timeout: 15_000 })

    await responder.page.getByTestId('resolve-assignment').click()
    await expect(home.page.getByTestId('test-incident-status')).toHaveText('resolved', { timeout: 15_000 })
    await expect(responder.page.getByTestId('responder-current-status')).toHaveText('available', { timeout: 15_000 })
    await expect(responder.page.getByTestId('no-active-assignment')).toBeVisible()
  } finally {
    const reset = home.page.getByTestId('reset-test-incident')
    if (await reset.isVisible().catch(() => false)) {
      await reset.click()
      await expect(home.page.getByTestId('incidents-empty')).toBeVisible({ timeout: 15_000 })
    }
  }
})
