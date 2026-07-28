// Integration test for the client-side MCP execution loop. A delegated MCP
// function call is executed through /api/mcp and its result is chained back to
// the Responses API.
import { test, expect } from '@playwright/test';
import http from 'node:http';
import { sendChatMessage } from './helpers';

const TOOL_OUTPUT = 'chain-ok-42: the warehouse holds 17 crates';
let mcpServer;
let mcpPort;
let mcpCalls = [];

test.beforeAll(async () => {
  mcpServer = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      let rpc = {};
      try { rpc = JSON.parse(body); } catch { /* malformed input remains empty */ }
      mcpCalls.push(rpc);
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({
        jsonrpc: '2.0',
        id: rpc.id ?? null,
        result: { content: [{ type: 'text', text: TOOL_OUTPUT }] },
      }));
    });
  });
  await new Promise((resolve) => mcpServer.listen(0, '127.0.0.1', resolve));
  mcpPort = mcpServer.address().port;
});

test.afterAll(async () => {
  await new Promise((resolve) => mcpServer.close(resolve));
});

test('function_call delegation runs the configured MCP tool and chains the answer', async ({ page }) => {
  mcpCalls = [];
  await page.addInitScript(({ port }) => {
    localStorage.setItem('mcpServers', JSON.stringify([{
      id: 'srv-test', name: 'echo srv', endpoint: `http://127.0.0.1:${port}/mcp`,
      enabled: true, authType: 'none',
    }]));
  }, { port: mcpPort });
  await page.route('**/api/conversations', (route) =>
    route.fulfill({ json: { id: 'conv-chain-test', metadata: {} } }));
  await page.route('**/api/generate-title', (route) =>
    route.fulfill({ json: { title: 'Chain test' } }));

  let responsesCalls = 0;
  let chainedBody = null;
  await page.route('**/api/responses', (route) => {
    responsesCalls += 1;
    if (responsesCalls === 1) {
      return route.fulfill({
        contentType: 'text/event-stream',
        body: [
          { response_id: 'resp_test_1' },
          { mcp_function_call: {
            item_id: 'fc_test_1', call_id: 'call_test_1',
            fn_name: 'mcp__echo_srv__lookup_inventory', server_label: 'echo_srv',
            tool_name: 'lookup_inventory', arguments: '{"warehouse":"north"}',
          } },
          { done: true },
        ].map(JSON.stringify).join('\n') + '\n',
      });
    }
    chainedBody = route.request().postDataJSON();
    return route.fulfill({
      contentType: 'text/event-stream',
      body: [
        { response_id: 'resp_test_2' },
        { text: 'The north warehouse holds 17 crates.' },
        { done: true },
      ].map(JSON.stringify).join('\n') + '\n',
    });
  });

  await page.goto('/');
  await sendChatMessage(page, 'How many crates in the north warehouse?');
  await expect(page.getByText('The north warehouse holds 17 crates.')).toBeVisible({ timeout: 30_000 });

  expect(mcpCalls.map((call) => call.method)).toEqual(['initialize', 'tools/call']);
  expect(mcpCalls[1].params).toEqual({ name: 'lookup_inventory', arguments: { warehouse: 'north' } });
  expect(responsesCalls).toBe(2);
  const functionOutput = (chainedBody?.input || []).find((item) => item.type === 'function_call_output');
  expect(functionOutput?.call_id).toBe('call_test_1');
  expect(functionOutput?.output).toContain(TOOL_OUTPUT);
});
