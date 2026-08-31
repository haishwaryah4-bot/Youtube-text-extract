const puppeteer = require('puppeteer');
(async () => {
  try {
    const browser = await puppeteer.launch({headless: "new"});
    const page = await browser.newPage();
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.log('PAGE ERROR:', err.toString()));
    await page.goto('http://127.0.0.1:8000/');
    await page.type('#youtubeUrl', 'https://youtu.be/s30Z-PD1Iq8?si=KepZ2nvkJFYbGCOg');
    await page.click('#btnProcess');
    
    console.log('Waiting for resultsSection to not be hidden...');
    // wait for either results or error section to be shown
    await page.waitForFunction(() => {
        return !document.querySelector('#resultsSection').classList.contains('hidden') || 
               !document.querySelector('#errorSection').classList.contains('hidden');
    }, {timeout: 60000});
    
    console.log('Results or Error loaded, checking errors...');
    const hasError = await page.evaluate(() => !document.querySelector('#errorSection').classList.contains('hidden'));
    if (hasError) {
        const errorText = await page.evaluate(() => document.querySelector('#errorMessage').innerText);
        console.log('UI Error:', errorText);
    }
    
    // Check browser console errors
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    
    await browser.close();
  } catch (e) {
    console.error(e);
    process.exit(1);
  }
})();
