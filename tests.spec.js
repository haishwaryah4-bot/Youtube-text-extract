const { test, expect } = require('@playwright/test');

test.describe('Manual Transcript Fallback Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Go to the local app
    await page.goto('http://localhost:8000');
  });

  test('1. captions unavailable - shows fallback UI', async ({ page }) => {
    // Mock the API to return captions_unavailable
    await page.route('/api/youtube/analyze', async route => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          transcript_status: 'captions_unavailable',
          error: 'Captions are unavailable'
        })
      });
    });

    await page.fill('#youtubeUrl', 'https://www.youtube.com/watch?v=gB_dBDdKRBc');
    await page.click('#btnProcess');

    // Verify error section becomes visible
    await expect(page.locator('#errorSection')).not.toHaveClass(/hidden/);
    await expect(page.locator('#errorMessage')).toContainText('This video has no public captions');
    
    // Verify fallback textarea is visible and empty
    const manualInput = page.locator('#manualTranscriptInput');
    await expect(manualInput).toBeVisible();
    await expect(manualInput).toHaveValue('');
  });

  test('2. rate-limited retrieval - shows fallback UI', async ({ page }) => {
    // Mock the API to return rate_limited
    await page.route('/api/youtube/analyze', async route => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          transcript_status: 'rate_limited',
          error: 'Rate limited'
        })
      });
    });

    await page.fill('#youtubeUrl', 'https://www.youtube.com/watch?v=gB_dBDdKRBc');
    await page.click('#btnProcess');

    await expect(page.locator('#errorSection')).not.toHaveClass(/hidden/);
    await expect(page.locator('#errorMessage')).toContainText('YouTube temporarily blocked automated transcript retrieval');
    
    // Verify fallback textarea is visible and empty
    const manualInput = page.locator('#manualTranscriptInput');
    await expect(manualInput).toBeVisible();
    await expect(manualInput).toHaveValue('');
  });

  test('3. pasted URL rejection - frontend validation', async ({ page }) => {
    // Setup fallback UI by triggering a failure first
    await page.route('/api/youtube/analyze', async route => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          transcript_status: 'captions_unavailable'
        })
      });
    });

    await page.fill('#youtubeUrl', 'https://www.youtube.com/watch?v=gB_dBDdKRBc');
    await page.click('#btnProcess');
    
    // Now paste a URL into the manual transcript box
    await page.fill('#manualTranscriptInput', 'https://www.youtube.com/watch?v=gB_dBDdKRBc');
    await page.click('#btnSubmitManual');
    
    // Ensure the textarea still has the URL (preserved)
    await expect(page.locator('#manualTranscriptInput')).toHaveValue('https://www.youtube.com/watch?v=gB_dBDdKRBc');
    
    // Ensure the results section is still hidden because validation stopped it
    await expect(page.locator('#resultsSection')).toHaveClass(/hidden/);
  });

  test('4. valid pasted transcript success', async ({ page }) => {
    // 1st request: fail to trigger fallback
    // 2nd request: succeed with manual transcript
    let requestCount = 0;
    
    await page.route('/api/youtube/analyze', async route => {
      requestCount++;
      if (requestCount === 1) {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            transcript_status: 'captions_unavailable'
          })
        });
      } else {
        // Assert the payload contains the manual transcript
        const payload = JSON.parse(route.request().postData());
        expect(payload.transcript).toContain('This is a valid transcript with more than twenty words');
        
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            video_id: 'gB_dBDdKRBc',
            title: 'Mock Video',
            transcript_status: 'success',
            demonstrated_actions: [],
            recommended_actions: []
          })
        });
      }
    });

    await page.fill('#youtubeUrl', 'https://www.youtube.com/watch?v=gB_dBDdKRBc');
    await page.click('#btnProcess');
    
    // Wait for fallback UI
    await expect(page.locator('#manualTranscriptInput')).toBeVisible();
    
    // Paste valid text (> 20 words)
    const validText = "This is a valid transcript with more than twenty words so it passes the frontend validation. We just need to type a bit more to make sure it definitely hits the twenty word limit without any issues at all.";
    await page.fill('#manualTranscriptInput', validText);
    await page.click('#btnSubmitManual');
    
    // Verify it succeeded and showed results
    await expect(page.locator('#resultsSection')).not.toHaveClass(/hidden/);
    await expect(page.locator('#errorSection')).toHaveClass(/hidden/);
  });
});