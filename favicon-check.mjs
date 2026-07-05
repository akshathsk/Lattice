import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1440, height: 900 });
await page.goto('http://localhost:3000');
await page.waitForTimeout(2000);
// Grab the favicon link from DOM
const favHref = await page.$eval('link[rel="icon"]', el => el.href).catch(() => 'not found');
console.log('favicon href:', favHref);
await page.screenshot({ path: '/tmp/tab-favicon.png' });
await browser.close();
