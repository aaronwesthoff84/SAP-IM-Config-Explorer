import { defineConfig, devices } from '@playwright/test';
import fs from 'node:fs';

const venvPython = process.platform === 'win32'
  ? (fs.existsSync('.\\.venv\\Scripts\\python.exe') ? '.\\.venv\\Scripts\\python.exe' : 'python')
  : (fs.existsSync('./.venv/bin/python') ? './.venv/bin/python' : 'python');

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: process.env.CI ? 1 : undefined,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: `${venvPython} -m uvicorn sap_im_config_graph_explorer.app:app --host 127.0.0.1 --port 8000`,
    url: 'http://127.0.0.1:8000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
