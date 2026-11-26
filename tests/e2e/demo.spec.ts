import { test, expect } from './fixtures';

test('demo role navigation stays visibly synthetic and never calls the API',async({page})=>{
  const apiRequests:string[]=[];
  page.on('request',request=>{if(request.url().includes('/api/v1/'))apiRequests.push(request.url());});
  await page.goto('/');
  await expect(page.getByRole('status')).toContainText('Offline demonstration');
  for(const [role,path] of [['Teacher','teacher'],['Student','student'],['Parent','parent']]) {
    await page.getByRole('button',{name:role,exact:true}).click();
    await expect(page).toHaveURL(new RegExp('/'+path+'/dashboard'));
    await expect(page.getByRole('status')).toContainText('synthetic data only');
  }
  expect(apiRequests).toEqual([]);
});
