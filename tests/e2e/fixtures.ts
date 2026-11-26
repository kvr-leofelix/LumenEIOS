import { test as base, expect } from '@playwright/test';

// A stale build must never send test logins or writes to a real/original backend.
export const test=base.extend({
  page:async({page},use)=>{
    await page.route('**/*',route=>{
      const origin=new URL(route.request().url()).origin;
      return ['http://127.0.0.1:14173','http://127.0.0.1:18080'].includes(origin)
        ? route.continue() : route.abort('blockedbyclient');
    });
    await use(page);
  }
});
export { expect };
