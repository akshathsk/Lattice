import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1440, height: 900 });

// Home page
await page.goto('http://localhost:3000');
await page.waitForTimeout(3000);
await page.screenshot({ path: '/tmp/home-new.png' });
console.log('Home done');

// Connectors
const connEl = await page.getByText('Connectors', { exact: true }).first();
await connEl.click();
await page.waitForTimeout(2000);
await page.screenshot({ path: '/tmp/connectors2-new.png', fullPage: true });
console.log('Connectors done');

await browser.close();
