// Text-to-SQL is request-scoped: the selected semantic stores are forwarded to
// the REST application as a semantic_store tool. No hosted DBTools MCP endpoint
// or browser OAuth token is needed.
import { test, expect } from '@playwright/test';
import { sendChatMessage } from './helpers';

const STORE_ID = 'ocid1.semanticstore.test.store1';

async function captureResponsesPayload(page, ids) {
  await page.addInitScript((semanticStoreIds) => {
    localStorage.setItem('nativeToolsEnabled', JSON.stringify({ native_text_to_sql: true }));
    localStorage.setItem('nl2sqlSemanticStoreIds', JSON.stringify(semanticStoreIds));
  }, ids);
  await page.route('**/api/conversations', (route) =>
    route.fulfill({ json: { id: 'conv-nl2sql-test', metadata: {} } }));
  await page.route('**/api/generate-title', (route) =>
    route.fulfill({ json: { title: 'NL2SQL test' } }));

  let payload = null;
  await page.route('**/api/responses', (route) => {
    payload = route.request().postDataJSON();
    return route.fulfill({
      contentType: 'text/event-stream',
      body: `${JSON.stringify({ response_id: 'resp_nl2sql' })}\n${JSON.stringify({ text: 'Here is your data.' })}\n${JSON.stringify({ done: true })}\n`,
    });
  });

  await page.goto('/');
  await sendChatMessage(page, 'How many orders did we ship last month?');
  await expect(page.getByText('Here is your data.')).toBeVisible({ timeout: 30_000 });
  return payload;
}

test('attaches selected semantic stores without a hosted MCP tool', async ({ page }) => {
  const payload = await captureResponsesPayload(page, [STORE_ID]);
  const tool = (payload?.tools || []).find((item) => item.type === 'semantic_store');

  expect(tool).toEqual({ type: 'semantic_store', semantic_store_ids: [STORE_ID] });
  expect((payload?.tools || []).some((item) => item.server_label === 'Nl2Sql')).toBe(false);
  expect(payload.systemPrompt).not.toContain('generate_sql');
});

test('does not attach a semantic store when none is selected', async ({ page }) => {
  const payload = await captureResponsesPayload(page, []);
  expect((payload?.tools || []).some((item) => item.type === 'semantic_store')).toBe(false);
});
