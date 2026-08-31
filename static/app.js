// TubeAction AI - Core Client Application

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Lucide icons
  if (window.lucide) {
    lucide.createIcons();
  }

  // Handle timestamp link clicks to seek the video player
  document.addEventListener('click', (e) => {
    const target = e.target.closest('.timestamp-link');
    if (target) {
      const secs = parseInt(target.dataset.seconds, 10);
      if (!isNaN(secs)) {
        if (ytPlayer && typeof ytPlayer.seekTo === 'function') {
          try {
            ytPlayer.seekTo(secs, true);
            ytPlayer.playVideo();
            showToast(`Jumped video to timestamp`);
          } catch (err) {
            console.error("Error seeking video:", err);
          }
        } else if (videoIframe && currentVideoId) {
          // Fallback if player API not ready
          videoIframe.src = `https://www.youtube-nocookie.com/embed/${currentVideoId}?enablejsapi=1&autoplay=1&start=${secs}&origin=${encodeURIComponent(window.location.origin)}`;
          showToast(`Jumped video to timestamp`);
        }
      }
    }
  });

  // DOM Elements
  const processForm = document.getElementById('processForm');
  const youtubeUrlInput = document.getElementById('youtubeUrl');
  const btnPaste = document.getElementById('btnPaste');
  const btnClear = document.getElementById('btnClear');
  const btnProcess = document.getElementById('btnProcess');
  const samplePills = document.querySelectorAll('.sample-chip');
  const urlValidationStatus = document.getElementById('urlValidationStatus');

  const progressSection = document.getElementById('progressSection');
  const progressTimer = document.getElementById('progressTimer');
  const currentProgressTitle = document.getElementById('currentProgressTitle');
  const currentProgressSub = document.getElementById('currentProgressSub');
  const errorSection = document.getElementById('errorSection');
  const errorTitle = document.getElementById('errorTitle');
  const errorMessage = document.getElementById('errorMessage');
  const btnRetry = document.getElementById('btnRetry');

  const resultsSection = document.getElementById('resultsSection');
  const resultsWarningBanner = document.getElementById('resultsWarningBanner');
  const resultsWarningText = document.getElementById('resultsWarningText');
  const videoIframe = document.getElementById('videoIframe');
  const displayVideoTitle = document.getElementById('displayVideoTitle');
  const displayVideoAuthor = document.getElementById('displayVideoAuthor');
  const badgeWordCount = document.getElementById('badgeWordCount');
  const badgeActionCount = document.getElementById('badgeActionCount');
  const btnDownloadPdf = document.getElementById('btnDownloadPdf');
  const btnJumpPdfTab = document.getElementById('btnJumpPdfTab');
  const btnJumpChecklist = document.getElementById('btnJumpChecklist');

  // Tabs
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');
  const tabBadgeActions = document.getElementById('tabBadgeActions');
  const tabBadgeChecklist = document.getElementById('tabBadgeChecklist');

  // Summary Pane Elements
  const overviewContent = document.getElementById('overviewContent');
  const mainTopicsList = document.getElementById('mainTopicsList');
  const factsList = document.getElementById('factsList');
  const explanationsList = document.getElementById('explanationsList');
  const recommendationsList = document.getElementById('recommendationsList');
  const finalSummaryContent = document.getElementById('finalSummaryContent');

  // Actions Pane Elements
  const actionsList = document.getElementById('actionsList');

  // Checklist Pane Elements
  const checklistContainer = document.getElementById('checklistContainer');
  const checklistProgressText = document.getElementById('checklistProgressText');
  const checklistProgressBar = document.getElementById('checklistProgressBar');
  const btnResetChecklist = document.getElementById('btnResetChecklist');
  const btnCopyChecklist = document.getElementById('btnCopyChecklist');

  // PDF Viewer Elements
  const pdfIframe = document.getElementById('pdfIframe');
  const pdfFileName = document.getElementById('pdfFileName');
  const btnPdfDownloadDirect = document.getElementById('btnPdfDownloadDirect');
  const btnPdfOpenNewTab = document.getElementById('btnPdfOpenNewTab');

  // Panel Tab Elements
  const btnShowSummary = document.getElementById('btnShowSummary');
  const btnShowActions = document.getElementById('btnShowActions');
  const btnShareVideo = document.getElementById('btnShareVideo');

  // Transcript Elements
  const transcriptContent = document.getElementById('transcriptContent');
  const transcriptSearch = document.getElementById('transcriptSearch');
  const btnCopyTranscript = document.getElementById('btnCopyTranscript');

  // Settings Modal
  const btnSettings = document.getElementById('btnSettings');
  const settingsModal = document.getElementById('settingsModal');
  const btnCloseModal = document.getElementById('btnCloseModal');
  const btnSaveSettings = document.getElementById('btnSaveSettings');
  const apiKeyInput = document.getElementById('apiKeyInput');

  // Manual fallback elements
  const btnSubmitManual = document.getElementById('btnSubmitManual');
  const manualTranscriptInput = document.getElementById('manualTranscriptInput');
  const btnSampleTranscript = document.getElementById('btnSampleTranscript');

  // --- Application State ---
  let timerInterval = null;
  let timerSeconds = 0;
  let currentVideoId = null;
  let userApiKey = localStorage.getItem('tubeaction_openai_key') || '';
  let stepperTimeouts = [];
  let ytPlayer = null;
  let timeSyncInterval = null;
  let currentData = null;      // last successful API response
  let activePanelTab = 'summary';

  // Load YouTube IFrame Player API dynamically
  if (!window.YT) {
    const tag = document.createElement('script');
    tag.src = "https://www.youtube.com/iframe_api";
    const firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
  }

  if (apiKeyInput) {
    apiKeyInput.value = userApiKey;
  }

  function startPlaybackSync() {
    clearInterval(timeSyncInterval);
    timeSyncInterval = setInterval(() => {
      if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function') {
        try {
          const currentTime = ytPlayer.getCurrentTime();
          syncDashboardPlayback(currentTime);
        } catch (e) {
          // Ignore
        }
      }
    }, 400);
  }

  function stopPlaybackSync() {
    clearInterval(timeSyncInterval);
  }

  function onPlayerStateChange(event) {
    if (event.data === 1) { // YT.PlayerState.PLAYING
      startPlaybackSync();
    } else {
      stopPlaybackSync();
    }
  }

  function syncDashboardPlayback(currentTime) {
    const summaryActionsContent = document.getElementById('summaryActionsContent');
    if (!summaryActionsContent) return;

    const segments = summaryActionsContent.querySelectorAll('.segment-block, .step-segment');
    let activeSeg = null;
    let maxSeconds = -1;

    segments.forEach((seg) => {
      const secs = parseInt(seg.dataset.seconds, 10);
      if (!isNaN(secs) && secs <= currentTime && secs > maxSeconds) {
        maxSeconds = secs;
        activeSeg = seg;
      }
    });

    if (activeSeg) {
      const alreadyActive = activeSeg.classList.contains('active');
      if (!alreadyActive) {
        segments.forEach((s) => s.classList.remove('active'));
        activeSeg.classList.add('active');
        // Scroll within the right-column panel, not the page
        const rightCol = document.querySelector('.right-column');
        if (rightCol) {
          const segTop = activeSeg.offsetTop - summaryActionsContent.offsetTop;
          const panelScrollTop = rightCol.scrollTop;
          const panelHeight = rightCol.clientHeight;
          // Only scroll if the segment is out of view within the panel
          if (segTop < panelScrollTop + 80 || segTop > panelScrollTop + panelHeight - 80) {
            rightCol.scrollTo({ top: segTop - 80, behavior: 'smooth' });
          }
        } else {
          activeSeg.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      }
    }
  }

  // --- Utility Functions ---
  function showToast(msg) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
  }

  function startTimer() {
    timerSeconds = 0;
    progressTimer.textContent = '00:00';
    clearInterval(timerInterval);
    timerInterval = setInterval(() => {
      timerSeconds++;
      const mins = String(Math.floor(timerSeconds / 60)).padStart(2, '0');
      const secs = String(timerSeconds % 60).padStart(2, '0');
      progressTimer.textContent = `${mins}:${secs}`;
    }, 1000);
  }

  function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
    clearStepperTimeouts();
  }

  function clearStepperTimeouts() {
    stepperTimeouts.forEach(t => clearTimeout(t));
    stepperTimeouts = [];
  }

  function setProcessingState(processing) {
    btnProcess.disabled = processing;
    if (btnSubmitManual) btnSubmitManual.disabled = processing;
    if (youtubeUrlInput) youtubeUrlInput.disabled = processing;
    if (manualTranscriptInput) manualTranscriptInput.disabled = processing;
    if (btnPaste) btnPaste.disabled = processing;
    if (btnClear) btnClear.disabled = processing;
    samplePills.forEach(pill => {
      pill.disabled = processing;
      if (processing) {
        pill.classList.add('disabled');
      } else {
        pill.classList.remove('disabled');
      }
    });
  }

  function updateStepper(activeStep, title, sub) {
    currentProgressTitle.textContent = title;
    currentProgressSub.textContent = sub;

    const stepNodes = document.querySelectorAll('.step-node');
    const stepLines = document.querySelectorAll('.step-line');

    stepNodes.forEach((node) => {
      const step = parseInt(node.dataset.step, 10);
      node.classList.remove('active', 'completed');
      if (step < activeStep) {
        node.classList.add('completed');
      } else if (step === activeStep) {
        node.classList.add('active');
      }
    });

    stepLines.forEach((line) => {
      const lineStep = parseInt(line.dataset.line, 10);
      line.classList.remove('completed');
      if (lineStep < activeStep) {
        line.classList.add('completed');
      }
    });
  }

  // --- Input Management ---
  youtubeUrlInput.addEventListener('input', () => {
    const val = youtubeUrlInput.value.trim();
    btnClear.classList.toggle('hidden', !val);
  });

  btnClear.addEventListener('click', () => {
    youtubeUrlInput.value = '';
    btnClear.classList.add('hidden');
    urlValidationStatus.classList.add('hidden');
    youtubeUrlInput.focus();
  });

  btnPaste.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        youtubeUrlInput.value = text.trim();
        btnClear.classList.remove('hidden');
        processVideo(text.trim());
      }
    } catch (e) {
      showToast('Unable to read clipboard. Please paste manually.');
    }
  });

  samplePills.forEach((pill) => {
    pill.addEventListener('click', () => {
      const url = pill.dataset.url;
      youtubeUrlInput.value = url;
      btnClear.classList.remove('hidden');
      processVideo(url);
    });
  });

  // --- Settings Modal ---
  btnSettings.addEventListener('click', () => {
    settingsModal.classList.remove('hidden');
  });

  btnCloseModal.addEventListener('click', () => {
    settingsModal.classList.remove('hidden');
  });

  btnSaveSettings.addEventListener('click', () => {
    userApiKey = apiKeyInput.value.trim();
    localStorage.setItem('tubeaction_openai_key', userApiKey);
    settingsModal.classList.add('hidden');
    showToast(userApiKey ? 'OpenAI API key saved.' : 'Using default backend settings.');
  });



  if (btnSubmitManual && manualTranscriptInput) {
    btnSubmitManual.addEventListener('click', async () => {
      let url = youtubeUrlInput.value.trim();
      const text = manualTranscriptInput.value.trim();
      
      if (!url) {
        url = "https://www.youtube.com/watch?v=sample12345";
      }

      if (text) {
        // Validation: Ensure the pasted text is not a URL
        if (text.match(/^https?:\/\/(www\.)?(youtube\.com|youtu\.be)/i)) {
          showToast('Please paste transcript text, not a YouTube URL.');
          return;
        }
      } else {
        showToast('Please paste the transcript text first.');
        return;
      }
      
      const lowerText = text.toLowerCase();
      if (lowerText.startsWith('http://') || lowerText.startsWith('https://') || lowerText.includes('youtube.com/') || lowerText.includes('youtu.be/')) {
        showToast('Please paste transcript text, not a YouTube URL.');
        return;
      }

      // Validate length and reject if it's just a URL
      const textWithoutUrls = text.replace(/https?:\/\/\S+/gi, '').trim();
      const wordCount = textWithoutUrls.split(/\s+/).filter(Boolean).length;
      
      if (wordCount < 10) {
        showToast('Paste the actual spoken transcript from the video, not the YouTube link.');
        return;
      }

      processVideo(url, text);
    });
  }

  if (btnSampleTranscript && manualTranscriptInput) {
    btnSampleTranscript.addEventListener('click', () => {
      manualTranscriptInput.value = "Modern farming uses technology to improve crop production and reduce waste. Farmers can use sensors to monitor soil moisture and crop conditions. Drip irrigation delivers water directly to plant roots and can reduce water loss. Weather information helps farmers decide when to irrigate and protect crops. Precision agriculture uses data to apply water, fertilizer, and other inputs more efficiently.";
      showToast('Sample transcript loaded.');
    });
  }

  // --- Main Video Processing Pipeline ---
  processForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const url = youtubeUrlInput.value.trim();
    if (url) {
      processVideo(url);
    }
  });

  btnRetry.addEventListener('click', () => {
    const url = youtubeUrlInput.value.trim();
    if (url) {
      processVideo(url);
    }
  });

  async function processVideo(url, manualTranscript = null) {
    errorSection.classList.add('hidden');
    resultsSection.classList.add('hidden');
    progressSection.classList.remove('hidden');
    setProcessingState(true);

    startTimer();
    clearStepperTimeouts();

    // Stage 1: URL Validation
    updateStepper(1, 'Validating YouTube URL...', 'Checking URL format and video availability');

    try {
      stepperTimeouts.push(setTimeout(() => {
        if (!timerInterval) return;
        if (manualTranscript) {
          updateStepper(2, 'Using Custom Transcript...', 'Pasted text accepted successfully');
        } else {
          updateStepper(2, 'Fetching Captions or Transcribing Audio...', 'Retrieving or extracting audio transcripts');
        }
      }, 700));

      stepperTimeouts.push(setTimeout(() => {
        if (!timerInterval) return;
        updateStepper(3, 'Processing Video Content...', 'Analyzing full transcript context with LangGraph');
      }, 1800));

      stepperTimeouts.push(setTimeout(() => {
        if (!timerInterval) return;
        updateStepper(4, 'Generating complete summary...', 'Formulating overview & key points');
      }, 3000));

      stepperTimeouts.push(setTimeout(() => {
        if (!timerInterval) return;
        updateStepper(5, 'Extracting actions...', 'Distinguishing demonstrated vs recommended instructions');
      }, 4200));

      stepperTimeouts.push(setTimeout(() => {
        if (!timerInterval) return;
        updateStepper(6, 'Generating PDF Document...', 'Compiling professionally formatted report');
      }, 5500));

      // Call the standardized POST /api/youtube/analyze endpoint
      const bodyPayload = {
        youtube_url: url,
        api_key: userApiKey
      };
      if (manualTranscript) {
        bodyPayload.transcript = manualTranscript;
      }

      const response = await fetch('/api/youtube/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bodyPayload)
      });

      let data;
      try {
        data = await response.json();
      } catch (e) {
        throw new Error("Backend returned an invalid response (not JSON). The server might be down or experiencing a critical error.");
      }

      // Check if request or transcript retrieval failed
      if (!response.ok || !data.success || data.transcript_status !== 'success') {
        let userFacingError = 'Automatic transcript retrieval failed. You can paste the transcript below for instant free summarization.';
        
        // Only if the backend explicitly proved the video is completely inaccessible
        if (data.error_type === 'VIDEO_UNAVAILABLE') {
            // Keep the generic prompt so the user can still try pasting their own
        }

        throw new Error(userFacingError);
      }

      // Initialize chat context
      currentVideoId = data.video_id;
      chatHistory = [];

      // Stage 7: Complete
      updateStepper(7, 'Complete!', 'All summary sections and PDF report ready.');
      stepperTimeouts.push(setTimeout(() => {
        stopTimer();
        progressSection.classList.add('hidden');
        renderResults(data);
        setProcessingState(false);
        if (manualTranscriptInput) {
          manualTranscriptInput.value = ''; // clear paste text
        }
      }, 600));

    } catch (err) {
      stopTimer();
      progressSection.classList.add('hidden');
      errorSection.classList.remove('hidden');
      
      // Only clear the textarea if this was an automatic fetch failure. 
      // This ensures it's empty when the fallback first appears, 
      // but preserves the user's text if their manual submission fails.
      if (!manualTranscript && manualTranscriptInput) {
        manualTranscriptInput.value = '';
      }

      errorTitle.textContent = '⚠ Automatic transcript unavailable';
      errorMessage.textContent = err.message || 'Paste the video\'s transcript below and get a free instant summary.';
      setProcessingState(false);
      showToast(err.message);
    }
  }

  // --- Render Results ---
  function renderResults(data) {
    currentData = data;
    chatHistory = [];

    // Downstream error banner
    if (data.error && resultsWarningBanner && resultsWarningText) {
      resultsWarningText.textContent = data.error;
      resultsWarningBanner.classList.remove('hidden');
    } else if (resultsWarningBanner) {
      resultsWarningBanner.classList.add('hidden');
    }

    // Show the video and details in the left column
    let titleHtml = data.title || 'Untitled Video';
    if (data.is_local_fallback) {
      titleHtml += ` <span class="badge" style="background-color: var(--success); color: white; font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; margin-left: 8px; vertical-align: middle;">Free Local Summary Mode</span>`;
    }
    displayVideoTitle.innerHTML = titleHtml;
    displayVideoAuthor.textContent = data.author || 'Unknown Channel';
    
    // Embed Player
    if (data.video_id) {
      currentVideoId = data.video_id;
      videoIframe.src = `https://www.youtube.com/embed/${data.video_id}?enablejsapi=1`;
    } else {
      videoIframe.src = '';
    }

    const demonstrated = data.demonstrated_actions || [];
    const recommended = data.recommended_actions || [];
    const allActions = [...demonstrated, ...recommended];

    badgeWordCount.innerHTML = `<i data-lucide="align-left" class="icon-xxs"></i> Verified (${data.transcript_status || 'success'})`;
    badgeActionCount.innerHTML = `<i data-lucide="check-square" class="icon-xxs"></i> ${allActions.length} Actions`;

    videoIframe.src = `https://www.youtube-nocookie.com/embed/${data.video_id}?enablejsapi=1&origin=${encodeURIComponent(window.location.origin)}`;

    // Bind YouTube Player API on load
    videoIframe.onload = () => {
      if (window.YT && window.YT.Player) {
        try {
          if (ytPlayer && typeof ytPlayer.destroy === 'function') {
            ytPlayer.destroy();
          }
          ytPlayer = new YT.Player('videoIframe', {
            events: {
              'onReady': () => {
                // Immediately sync to current position (covers seek-while-paused)
                startPlaybackSync();
              },
              'onStateChange': onPlayerStateChange
            }
          });
        } catch (e) {
          console.error("Error initializing YT Player:", e);
        }
      }
    };

    // PDF links
    const pdfUrl = `/api/pdf/${data.video_id}`;
    const pdfDirectUrl = `${pdfUrl}?download=true`;
    if (btnDownloadPdf) {
      btnDownloadPdf.href = pdfDirectUrl;
    }

    // Enable sub-tab buttons
    if (btnShowSummary) btnShowSummary.disabled = false;
    if (btnShowActions) btnShowActions.disabled = false;

    // Render active panel tab content
    renderActivePanelTabContent(data);

    resultsSection.classList.remove('hidden');

    if (window.lucide) {
      lucide.createIcons();
    }
  }

  function parseTimestampToSeconds(text) {
    if (!text) return 0;
    // Try [HH:MM:SS] first
    let match = text.match(/\[(\d{1,2}):(\d{2}):(\d{2})\]/);
    if (match) {
      return parseInt(match[1], 10) * 3600 + parseInt(match[2], 10) * 60 + parseInt(match[3], 10);
    }
    // Try [MM:SS]
    match = text.match(/\[(\d{1,2}):(\d{2})\]/);
    if (match) {
      return parseInt(match[1], 10) * 60 + parseInt(match[2], 10);
    }
    return 0;
  }

  function linkifyTimestamps(text) {
    if (!text) return '';

    // Range: [MM:SS - MM:SS] or [H:MM:SS - H:MM:SS] — seek to start time
    const rangeReplace = (match, h1, m1, s1, h2, m2, s2) => {
      const startSecs = (h1 ? parseInt(h1,10)*3600 : 0) + parseInt(m1,10)*60 + parseInt(s1,10);
      return `<span class="timestamp-link" data-seconds="${startSecs}" style="cursor:pointer;color:#2563eb;font-weight:600;text-decoration:underline;">${match}</span>`;
    };

    // [H:MM:SS - H:MM:SS]
    let temp = text.replace(/\[(\d{1,2}):(\d{2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2}):(\d{2})\]/g,
      (match, h1, m1, s1, h2, m2, s2) => rangeReplace(match, h1, m1, s1, h2, m2, s2));

    // [MM:SS - MM:SS]
    temp = temp.replace(/\[(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\]/g,
      (match, m1, s1, m2, s2) => rangeReplace(match, null, m1, s1, null, m2, s2));

    // Single [HH:MM:SS]
    temp = temp.replace(/\[(\d{1,2}):(\d{2}):(\d{2})\]/g, (match, p1, p2, p3) => {
      const totalSecs = parseInt(p1,10)*3600 + parseInt(p2,10)*60 + parseInt(p3,10);
      return `<span class="timestamp-link" data-seconds="${totalSecs}" style="cursor:pointer;color:#2563eb;font-weight:600;text-decoration:underline;">${match}</span>`;
    });

    // Single [MM:SS]
    temp = temp.replace(/\[(\d{1,2}):(\d{2})\]/g, (match, p1, p2) => {
      const totalSecs = parseInt(p1,10)*60 + parseInt(p2,10);
      return `<span class="timestamp-link" data-seconds="${totalSecs}" style="cursor:pointer;color:#2563eb;font-weight:600;text-decoration:underline;">${match}</span>`;
    });

    return temp;
  }

  // Render a **Bold heading:** formatted overview string as rich HTML sections
  function renderFormattedOverview(text, container) {
    container.innerHTML = '';
    if (!text) return;

    // Split on double-newline section breaks
    const sections = text.split(/\n\n+/);

    sections.forEach(section => {
      const trimmed = section.trim();
      if (!trimmed) return;

      // Each section may start with **Heading:** pattern
      const headingMatch = trimmed.match(/^\*\*([^*]+):\*\*\s*/);

      const wrapper = document.createElement('div');
      wrapper.className = 'segment-block';

      // Determine the earliest timestamp in this section for playback sync
      const firstTS = parseTimestampToSeconds(trimmed);
      wrapper.dataset.seconds = firstTS;

      if (headingMatch) {
        const headingText = headingMatch[1].trim();
        const bodyRaw = trimmed.slice(headingMatch[0].length).trim();

        // Build heading row with optional leading timestamp for gutter
        const tsHHMMSS = trimmed.match(/\[(\d{1,2}):(\d{2}):(\d{2})\]/);
        const tsMMSS   = trimmed.match(/\[(\d{1,2}):(\d{2})\]/);
        const tsLabel  = tsHHMMSS ? tsHHMMSS[0] : (tsMMSS ? tsMMSS[0] : null);

        let html = `<div class="overview-heading">`;
        html += `<strong>${escapeHtml(headingText)}:</strong>`;
        if (tsLabel) html += ` <span class="timestamp-link" data-seconds="${firstTS}" style="cursor:pointer;color:#2563eb;font-size:0.8rem;font-weight:600;">${tsLabel}</span>`;
        html += `</div>`;

        // Body: check if it has bullet list lines (starts with -) or numbered lines
        const bodyLines = bodyRaw.split('\n').filter(l => l.trim());
        const isBullet   = bodyLines.some(l => l.trim().startsWith('-'));
        const isNumbered = bodyLines.some(l => /^\d+\./.test(l.trim()));

        if (isBullet) {
          html += '<ul class="overview-list">';
          bodyLines.forEach(l => {
            const clean = l.trim().replace(/^-\s*/, '');
            html += `<li>${linkifyTimestamps(escapeHtml(clean))}</li>`;
          });
          html += '</ul>';
        } else if (isNumbered) {
          html += '<ol class="overview-list">';
          bodyLines.forEach(l => {
            const clean = l.trim().replace(/^\d+\.\s*/, '');
            html += `<li>${linkifyTimestamps(escapeHtml(clean))}</li>`;
          });
          html += '</ol>';
        } else {
          html += `<div class="segment-text">${linkifyTimestamps(escapeHtml(bodyRaw))}</div>`;
        }

        wrapper.innerHTML = html;
      } else {
        // Plain paragraph — render lines with timestamps linkified
        const bodyLines = trimmed.split('\n').filter(l => l.trim());
        const isBullet   = bodyLines.some(l => l.trim().startsWith('-'));
        const isNumbered = bodyLines.some(l => /^\d+\./.test(l.trim()));

        let html = '';
        if (isBullet) {
          html = '<ul class="overview-list">';
          bodyLines.forEach(l => {
            const clean = l.trim().replace(/^-\s*/, '');
            html += `<li>${linkifyTimestamps(escapeHtml(clean))}</li>`;
          });
          html += '</ul>';
        } else if (isNumbered) {
          html = '<ol class="overview-list">';
          bodyLines.forEach(l => {
            const clean = l.trim().replace(/^\d+\.\s*/, '');
            html += `<li>${linkifyTimestamps(escapeHtml(clean))}</li>`;
          });
          html += '</ol>';
        } else {
          html = `<div class="segment-text">${linkifyTimestamps(escapeHtml(trimmed))}</div>`;
        }
        wrapper.innerHTML = html;
      }

      container.appendChild(wrapper);
    });
  }

  function parseTimestampToSecs(ts) {
    if (!ts) return 0;
    const clean = ts.replace(/[\[\]]/g, '').trim();
    const parts = clean.split(':').map(Number);
    if (parts.length === 2) {
      return parts[0] * 60 + parts[1];
    } else if (parts.length === 3) {
      return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
    return 0;
  }

  function formatSummaryText(text) {
    if (!text) return '';
    const escaped = escapeHtml(text);
    const linkified = linkifyTimestamps(escaped);
    return linkified.replace(/\n/g, '<br>');
  }

  function renderListItems(container, items) {
    container.innerHTML = '';
    if (!items || items.length === 0) {
      container.innerHTML = `<li class="text-dim">None mentioned.</li>`;
      return;
    }
    items.forEach((item) => {
      const li = document.createElement('li');
      li.innerHTML = linkifyTimestamps(escapeHtml(item));
      container.appendChild(li);
    });
  }

  function renderActions(demonstrated, recommended) {
    actionsList.innerHTML = '';
    const totalCount = (demonstrated?.length || 0) + (recommended?.length || 0);

    if (totalCount === 0) {
      actionsList.innerHTML = `<p class="text-muted">No explicit actionable steps were identified in the transcript.</p>`;
      return;
    }

    let globalIdx = 1;

    // Render Demonstrated Actions first
    (demonstrated || []).forEach((act) => {
      renderActionCard(act, 'demonstrated', globalIdx++);
    });

    // Render Recommended Actions next
    (recommended || []).forEach((act) => {
      renderActionCard(act, 'recommended', globalIdx++);
    });
  }

  function renderActionCard(act, type, idx) {
    const card = document.createElement('div');
    const isDemo = type === 'demonstrated';
    card.className = `action-card ${type}`;

    const typeLabel = isDemo ? 'Demonstrated in Video' : 'Recommended / Instructed';
    const typeTagClass = isDemo ? 'demonstrated' : 'recommended';

    // Steps HTML
    let stepsHtml = '';
    const steps = act.steps || [];
    if (steps.length > 0) {
      stepsHtml = `
        <div class="steps-section">
          <span class="steps-heading">Step-by-Step Instructions:</span>
          <div class="steps-list">
            ${steps.map((s, sIdx) => {
              if (typeof s === 'object' && s !== null) {
                const stepNum = s.step_number || (sIdx + 1);
                const what = s.what_to_do || '';
                const why = s.why_it_matters || '';
                const tools = s.tools_resources && s.tools_resources.length > 0 ? s.tools_resources.join(', ') : '';
                const cautions = s.prerequisites_cautions && s.prerequisites_cautions.length > 0 ? s.prerequisites_cautions.join(', ') : '';
                const ts = s.timestamp && s.timestamp !== 'unavailable' ? s.timestamp : '';
                
                return `
                  <div class="step-item" style="flex-direction: column; align-items: flex-start; gap: 0.5rem; padding: 1rem; background: rgba(255,255,255,0.02); border-radius: var(--radius-sm); border: 1px solid rgba(255,255,255,0.05); margin-bottom: 0.75rem; width: 100%; box-sizing: border-box;">
                    <div style="display: flex; align-items: center; justify-content: space-between; width: 100%; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 0.5rem; margin-bottom: 0.5rem;">
                      <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <div class="step-badge-num">${stepNum}</div>
                        <strong style="font-size: 0.9rem; color: var(--text-main);">${escapeHtml(what)}</strong>
                      </div>
                      ${ts ? `<span class="timestamp-link" data-seconds="${parseTimestampToSecs(ts)}" style="cursor: pointer; color: #2563eb; font-family: var(--font-mono); font-size: 0.8rem; background: rgba(37,99,235,0.1); padding: 0.15rem 0.4rem; border-radius: var(--radius-sm); text-decoration: underline; font-weight: 600;">${escapeHtml(ts)}</span>` : ''}
                    </div>
                    ${why ? `<div style="font-size: 0.8rem; color: var(--text-muted); text-align: left; width: 100%;"><b style="color: var(--text-main);">Why it matters:</b> ${escapeHtml(why)}</div>` : ''}
                    ${tools ? `<div style="font-size: 0.8rem; color: var(--text-muted); text-align: left; width: 100%;"><b style="color: var(--text-main);">Tools/Resources:</b> ${escapeHtml(tools)}</div>` : ''}
                    ${cautions ? `<div style="font-size: 0.8rem; color: var(--text-muted); text-align: left; width: 100%;"><b style="color: var(--text-main);">Prerequisites/Cautions:</b> ${escapeHtml(cautions)}</div>` : ''}
                    ${s.evidence ? `<div style="font-size: 0.75rem; color: var(--text-muted); font-style: italic; background: rgba(0,0,0,0.2); padding: 0.4rem; border-left: 2px solid rgba(37,99,235,0.3); width: 100%; border-radius: 0 var(--radius-sm) var(--radius-sm) 0; box-sizing: border-box; text-align: left; margin-top: 0.25rem;"><b style="font-style: normal; color: var(--text-muted);">Source excerpt:</b> "${escapeHtml(s.evidence)}"</div>` : ''}
                  </div>
                `;
              } else {
                return `
                  <div class="step-item">
                    <div class="step-badge-num">${sIdx + 1}</div>
                    <div class="step-item-text">${linkifyTimestamps(escapeHtml(s))}</div>
                  </div>
                `;
              }
            }).join('')}
          </div>
        </div>
      `;
    }

    // Meta Pills HTML (tools, precautions, timing)
    let pillsHtml = '';
    if (act.tools_materials && act.tools_materials.length > 0) {
      const toolsStr = Array.isArray(act.tools_materials) ? act.tools_materials.join(', ') : act.tools_materials;
      pillsHtml += `<span class="meta-pill tools"><i data-lucide="wrench" class="icon-xxs"></i> <b>Tools/Materials:</b> ${escapeHtml(toolsStr)}</span>`;
    }
    if (act.precautions && act.precautions.length > 0) {
      const precStr = Array.isArray(act.precautions) ? act.precautions.join(', ') : act.precautions;
      pillsHtml += `<span class="meta-pill precautions"><i data-lucide="alert-circle" class="icon-xxs"></i> <b>Precautions:</b> ${escapeHtml(precStr)}</span>`;
    }
    if (act.timing_frequency) {
      pillsHtml += `<span class="meta-pill timing"><i data-lucide="clock" class="icon-xxs"></i> <b>Timing:</b> ${escapeHtml(act.timing_frequency)}</span>`;
    }

    card.innerHTML = `
      <div class="action-card-header">
        <div class="action-title-group">
          <div class="action-number">${idx}</div>
          <h4 class="action-name">${escapeHtml(act.name || 'Action Item')}</h4>
        </div>
        <span class="action-tag ${typeTagClass}">${typeLabel}</span>
      </div>

      <div class="action-details-block">
        <div class="detail-item">
          <div class="detail-item-title">What needs to be done</div>
          <div class="detail-item-desc">${escapeHtml(act.description || 'Follow instructions outlined in video.')}</div>
        </div>
        <div class="detail-item">
          <div class="detail-item-title">Why this is performed</div>
          <div class="detail-item-desc">${escapeHtml(act.why || 'To achieve the objective shown in the video.')}</div>
        </div>
      </div>

      ${stepsHtml}

      ${pillsHtml ? `<div class="action-extra-meta">${pillsHtml}</div>` : ''}
    `;

    actionsList.appendChild(card);
  }

  // --- Interactive Checklist ---
  function renderChecklist(checklistItems, videoId) {
    checklistContainer.innerHTML = '';
    const storageKey = `tubeaction_chk_${videoId}`;
    const savedState = JSON.parse(localStorage.getItem(storageKey) || '{}');

    if (!checklistItems || checklistItems.length === 0) {
      checklistContainer.innerHTML = `<p class="text-muted">No checklist items generated.</p>`;
      updateChecklistProgress(0, 0);
      return;
    }

    checklistItems.forEach((item, idx) => {
      const itemEl = document.createElement('div');
      const isChecked = !!savedState[idx];
      itemEl.className = `checklist-item ${isChecked ? 'checked' : ''}`;
      itemEl.dataset.index = idx;

      itemEl.innerHTML = `
        <div class="custom-checkbox">
          ${isChecked ? '<i data-lucide="check" class="icon-xs"></i>' : ''}
        </div>
        <span class="checklist-label">${escapeHtml(item)}</span>
      `;

      itemEl.addEventListener('click', () => {
        const nowChecked = !itemEl.classList.contains('checked');
        itemEl.classList.toggle('checked', nowChecked);
        savedState[idx] = nowChecked;
        localStorage.setItem(storageKey, JSON.stringify(savedState));

        const box = itemEl.querySelector('.custom-checkbox');
        box.innerHTML = nowChecked ? '<i data-lucide="check" class="icon-xs"></i>' : '';
        if (window.lucide) lucide.createIcons();

        updateChecklistProgress(
          checklistContainer.querySelectorAll('.checklist-item.checked').length,
          checklistItems.length
        );
      });

      checklistContainer.appendChild(itemEl);
    });

    const checkedCount = checklistContainer.querySelectorAll('.checklist-item.checked').length;
    updateChecklistProgress(checkedCount, checklistItems.length);

    btnResetChecklist.onclick = () => {
      localStorage.removeItem(storageKey);
      renderChecklist(checklistItems, videoId);
    };

    btnCopyChecklist.onclick = () => {
      const text = checklistItems.map((item, idx) => {
        const checked = savedState[idx] ? '[x]' : '[ ]';
        return `${checked} ${item}`;
      }).join('\n');
      navigator.clipboard.writeText(text);
      showToast('Checklist copied to clipboard!');
    };
  }

  function updateChecklistProgress(checked, total) {
    const pct = total > 0 ? Math.round((checked / total) * 100) : 0;
    checklistProgressText.textContent = `${checked} of ${total} completed (${pct}%)`;
    checklistProgressBar.style.width = `${pct}%`;
  }

  // --- Raw Transcript & Jump to Time ---
  function renderTranscript(rawText) {
    transcriptContent.innerHTML = '';
    if (!rawText) {
      transcriptContent.innerHTML = `<p class="text-muted">No raw transcript available.</p>`;
      return;
    }

    const lines = rawText.split('\n');
    lines.forEach((line) => {
      if (!line.trim()) return;
      const lineEl = document.createElement('div');
      lineEl.className = 'transcript-line';

      const match = line.match(/^\[(\d{2}):(\d{2})\]\s*(.*)$/);
      if (match) {
        const mins = parseInt(match[1], 10);
        const secs = parseInt(match[2], 10);
        const totalSecs = mins * 60 + secs;
        const text = match[3];

        lineEl.innerHTML = `
          <span class="transcript-time" data-seconds="${totalSecs}">[${match[1]}:${match[2]}]</span>
          <span class="transcript-text">${escapeHtml(text)}</span>
        `;

        lineEl.querySelector('.transcript-time').addEventListener('click', () => {
          if (ytPlayer && typeof ytPlayer.seekTo === 'function') {
            try {
              ytPlayer.seekTo(totalSecs, true);
              ytPlayer.playVideo();
              showToast(`Jumped video to ${match[1]}:${match[2]}`);
              return;
            } catch (e) {
              console.error("Error seeking via YT Player:", e);
            }
          }
          if (videoIframe && currentVideoId) {
            videoIframe.src = `https://www.youtube-nocookie.com/embed/${currentVideoId}?enablejsapi=1&autoplay=1&start=${totalSecs}&origin=${encodeURIComponent(window.location.origin)}`;
            showToast(`Jumped video to ${match[1]}:${match[2]}`);
          }
        });
      } else {
        lineEl.innerHTML = `<span class="transcript-text">${escapeHtml(line)}</span>`;
      }

      transcriptContent.appendChild(lineEl);
    });

    transcriptSearch.oninput = () => {
      const q = transcriptSearch.value.toLowerCase();
      const allLines = transcriptContent.querySelectorAll('.transcript-line');
      allLines.forEach((l) => {
        l.style.display = l.textContent.toLowerCase().includes(q) ? 'flex' : 'none';
      });
    };

    btnCopyTranscript.onclick = () => {
      navigator.clipboard.writeText(rawText);
      showToast('Transcript copied to clipboard!');
    };
  }

  // --- Share Button ---
  if (btnShareVideo) {
    btnShareVideo.addEventListener('click', () => {
      const url = youtubeUrlInput.value.trim();
      if (url) {
        navigator.clipboard.writeText(url);
        showToast('Video link copied to clipboard!');
      } else {
        showToast('No video link available.');
      }
    });
  }

  // --- Sub-tabs Switching ---
  if (btnShowSummary && btnShowActions) {
    btnShowSummary.addEventListener('click', () => {
      activePanelTab = 'summary';
      btnShowSummary.classList.add('active');
      btnShowActions.classList.remove('active');
      renderActivePanelTabContent(currentData);
    });

    btnShowActions.addEventListener('click', () => {
      activePanelTab = 'actions';
      btnShowActions.classList.add('active');
      btnShowSummary.classList.remove('active');
      renderActivePanelTabContent(currentData);
    });
  }

  // Render a single video-summary section block
  function makeSummarySection(iconName, label, bodyHtml, accentClass) {
    const block = document.createElement('div');
    block.className = 'vs-section';
    block.innerHTML = `
      <div class="vs-section-header ${accentClass || ''}">
        <span class="vs-section-icon"><i data-lucide="${iconName}" class="icon-xs"></i></span>
        <span class="vs-section-label">${label}</span>
      </div>
      <div class="vs-section-body">${bodyHtml}</div>
    `;
    return block;
  }

  function renderVideoSummary(data, container) {
    container.innerHTML = '';

    const demonstrated = data.demonstrated_actions || [];
    const recommended = data.recommended_actions || [];
    const allActions = [...demonstrated, ...recommended];

    // ── 1. What the Video is About ──────────────────────────────────────────
    // Use the structured overview field. Strip raw **Heading:** markdown to
    // extract just the Context / Content Summary sentences.
    const overviewRaw = (data.overview || data.summary || '').trim();
    let aboutText = '';
    if (overviewRaw) {
      // Try to pull the Context section from bold-heading format
      const contextMatch = overviewRaw.match(/\*\*Context:\*\*\s*([^\n]+(?:\n(?!\*\*)[^\n]+)*)/i);
      const contentMatch = overviewRaw.match(/\*\*Content Summary:\*\*\s*([^\n]+(?:\n(?!\*\*)[^\n]+)*)/i);
      const contextText = contextMatch ? contextMatch[1].trim() : '';
      const contentText = contentMatch ? contentMatch[1].trim() : '';
      if (contextText && contentText) {
        aboutText = `${contextText} ${contentText}`;
      } else if (contextText) {
        aboutText = contextText;
      } else if (contentText) {
        aboutText = contentText;
      } else {
        // No bold-heading structure — use as plain paragraph (strip ** markers)
        aboutText = overviewRaw.replace(/\*\*[^*]+:\*\*/g, '').replace(/\n+/g, ' ').trim();
      }
    }

    if (aboutText) {
      container.appendChild(
        makeSummarySection(
          'video', 'What the Video is About',
          `<p class="vs-body-text">${linkifyTimestamps(escapeHtml(aboutText))}</p>`,
          'accent-cyan'
        )
      );
    }

    // ── 2. Main Topic / Context ──────────────────────────────────────────────
    const mainTopics = data.main_topics || [];
    if (mainTopics.length > 0) {
      let topicsHtml = '<ul class="vs-list">';
      mainTopics.forEach(t => {
        const topic = typeof t === 'object' ? (t.topic || '') : String(t);
        const explanation = typeof t === 'object' ? (t.explanation || '') : '';
        topicsHtml += `<li class="vs-list-item">`;
        if (topic) topicsHtml += `<strong>${escapeHtml(topic)}</strong>`;
        if (explanation) topicsHtml += ` — <span class="vs-sub">${linkifyTimestamps(escapeHtml(explanation))}</span>`;
        topicsHtml += `</li>`;
      });
      topicsHtml += '</ul>';
      container.appendChild(
        makeSummarySection('book-open', 'Main Topic / Context', topicsHtml, 'accent-indigo')
      );
    }

    // ── 3. Important Points (in order they appear) ───────────────────────────
    // Pull Key Moments from the overview's bullet list, then fall back to key_points
    const kp = data.key_points || {};
    const facts = kp.facts || [];
    const explanations = kp.explanations || [];
    const recommendations = kp.recommendations || [];

    // Also try to extract Key Moments bullets from overview
    const momentsMatch = overviewRaw.match(/\*\*Key Moments:\*\*([\s\S]*?)(?=\n\*\*|$)/i);
    const momentLines = momentsMatch
      ? momentsMatch[1].split('\n').map(l => l.trim()).filter(l => l.startsWith('-') || l.match(/^\d+\./)).map(l => l.replace(/^[-\d.]+\s*/, ''))
      : [];

    const allPoints = [...momentLines, ...facts, ...explanations];
    if (allPoints.length > 0) {
      let pointsHtml = '<ul class="vs-list">';
      allPoints.forEach(pt => {
        if (pt.trim()) {
          pointsHtml += `<li class="vs-list-item">${linkifyTimestamps(escapeHtml(pt.trim()))}</li>`;
        }
      });
      pointsHtml += '</ul>';
      container.appendChild(
        makeSummarySection('list', 'Important Points', pointsHtml, 'accent-emerald')
      );
    }

    // ── 4. Key Actions / Steps & Tools Mentioned ─────────────────────────────
    // Pull from the overview's Actions/Steps section and from action data
    const actionsMatch = overviewRaw.match(/\*\*Actions \/ Steps:\*\*([\s\S]*?)(?=\n\*\*|$)/i);
    const overviewActionLines = actionsMatch
      ? actionsMatch[1].split('\n').map(l => l.trim()).filter(l => l.match(/^\d+\./))
        .map(l => l.replace(/^\d+\.\s*/, ''))
      : [];

    // Collect tools from all actions
    const toolsSet = new Set();
    allActions.forEach(act => {
      (act.tools_materials || []).forEach(t => t && toolsSet.add(t));
      (act.steps || []).forEach(step => {
        if (typeof step === 'object') {
          (step.tools_resources || []).forEach(t => t && toolsSet.add(t));
        }
      });
    });

    // Build step lines from structured action steps
    const structuredStepLines = [];
    allActions.forEach(act => {
      (act.steps || []).forEach(step => {
        if (typeof step === 'object' && step.what_to_do) {
          const tsRaw = step.timestamp && step.timestamp !== 'unavailable' ? ` <span class="timestamp-link" data-seconds="${parseTimestampToSecs(step.timestamp)}" style="cursor:pointer;color:#06B6D4;font-family:var(--font-mono);font-size:0.78rem;text-decoration:underline;font-weight:600;">${escapeHtml(step.timestamp)}</span>` : '';
          const tools = (step.tools_resources || []).filter(Boolean);
          let lineHtml = escapeHtml(step.what_to_do) + tsRaw;
          if (tools.length > 0) {
            lineHtml += ` <em class="vs-tools-inline">— Tools: ${escapeHtml(tools.join(', '))}</em>`;
          }
          structuredStepLines.push(lineHtml);
        }
      });
    });

    // Prefer structured steps; fall back to overview action lines
    const finalStepLines = structuredStepLines.length > 0 ? structuredStepLines
      : overviewActionLines.map(l => linkifyTimestamps(escapeHtml(l)));

    if (finalStepLines.length > 0 || toolsSet.size > 0) {
      let actHtml = '';
      if (finalStepLines.length > 0) {
        actHtml += '<ol class="vs-ordered-list">';
        finalStepLines.forEach(l => { actHtml += `<li class="vs-list-item">${l}</li>`; });
        actHtml += '</ol>';
      }
      if (toolsSet.size > 0) {
        actHtml += '<div class="vs-tools-block"><span class="vs-tools-label"><i data-lucide="wrench" class="icon-xxs"></i> Tools & Resources mentioned:</span>';
        actHtml += '<div class="vs-tools-pills">';
        toolsSet.forEach(t => { actHtml += `<span class="vs-tool-pill">${escapeHtml(t)}</span>`; });
        actHtml += '</div></div>';
      }
      container.appendChild(
        makeSummarySection('zap', 'Key Actions / Steps & Tools', actHtml, 'accent-amber')
      );
    }

    // ── 5. Conclusions / Takeaways ───────────────────────────────────────────
    const finalSummary = (data.final_summary || '').trim();
    const recs = recommendations.filter(r => !r.includes('Transcript summary') && !r.includes('pasted transcript'));
    if (finalSummary || recs.length > 0) {
      let takeawayHtml = '';
      if (finalSummary && !finalSummary.includes('Transcript summary') && !finalSummary.includes('pasted transcript')) {
        takeawayHtml += `<p class="vs-body-text">${linkifyTimestamps(escapeHtml(finalSummary))}</p>`;
      }
      if (recs.length > 0) {
        takeawayHtml += '<ul class="vs-list">';
        recs.forEach(r => { takeawayHtml += `<li class="vs-list-item">${linkifyTimestamps(escapeHtml(r))}</li>`; });
        takeawayHtml += '</ul>';
      }
      if (takeawayHtml) {
        container.appendChild(
          makeSummarySection('check-circle', 'Conclusions & Takeaways', takeawayHtml, 'accent-emerald')
        );
      }
    }

    if (container.children.length === 0) {
      container.innerHTML = '<p class="text-muted" style="padding:1rem 0;">No summary sections could be generated for this video.</p>';
    }

    if (window.lucide) lucide.createIcons();
  }

  function renderActivePanelTabContent(data) {
    const summaryActionsContent = document.getElementById('summaryActionsContent');
    if (!summaryActionsContent) return;

    if (!data) {
      summaryActionsContent.innerHTML = '<p class="panel-loading">Generating analysis… please wait.</p>';
      return;
    }

    summaryActionsContent.innerHTML = '';
    const demonstrated = data.demonstrated_actions || [];
    const recommended = data.recommended_actions || [];
    const allActions = [...demonstrated, ...recommended];

    if (activePanelTab === 'summary') {
      renderVideoSummary(data, summaryActionsContent);
    } else {
      if (allActions.length > 0) {
        let globalStepNum = 1;
        allActions.forEach((act) => {
          const steps = act.steps || [];
          steps.forEach((step) => {
            const stepNum = step.step_number || globalStepNum;
            globalStepNum++;
            const what = (typeof step === 'object' ? step.what_to_do : step) || '';
            const seconds = parseTimestampToSeconds(step.timestamp || '');

            const stepDiv = document.createElement('div');
            stepDiv.className = 'step-segment';
            stepDiv.dataset.seconds = seconds;

            const tsRaw = step.timestamp && step.timestamp !== 'unavailable' ? step.timestamp : null;

            let innerHtml = `
              <div class="step-segment-title">
                <h4>Step ${stepNum}: ${escapeHtml(what)}</h4>
                ${tsRaw ? `<span class="step-segment-badge timestamp-link" data-seconds="${seconds}">${escapeHtml(tsRaw)}</span>` : ''}
              </div>
              <div class="step-segment-body">
            `;

            if (step.why_it_matters) {
              innerHtml += `<div class="step-meta-item"><span class="step-meta-label">Why:</span> ${escapeHtml(step.why_it_matters)}</div>`;
            }
            if (step.tools_resources && step.tools_resources.length > 0) {
              const tools = Array.isArray(step.tools_resources) ? step.tools_resources.join(', ') : step.tools_resources;
              innerHtml += `<div class="step-meta-item"><span class="step-meta-label">Tools:</span> ${escapeHtml(tools)}</div>`;
            }
            if (step.prerequisites_cautions && step.prerequisites_cautions.length > 0) {
              const cautions = Array.isArray(step.prerequisites_cautions) ? step.prerequisites_cautions.join(', ') : step.prerequisites_cautions;
              innerHtml += `<div class="step-meta-item"><span class="step-meta-label">Prerequisites/Warnings:</span> ${escapeHtml(cautions)}</div>`;
            }
            if (step.evidence) {
              innerHtml += `<div class="step-excerpt">"${escapeHtml(step.evidence)}"</div>`;
            }

            innerHtml += '</div>';
            stepDiv.innerHTML = innerHtml;
            summaryActionsContent.appendChild(stepDiv);
          });
        });
      } else {
        summaryActionsContent.innerHTML = '<p class="text-muted">No explicit actionable steps were identified in this video.</p>';
      }
    }
  }

  // --- Copy Buttons ---
  document.querySelectorAll('.btnCopy').forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.target;
      const targetEl = document.getElementById(targetId);
      if (targetEl) {
        navigator.clipboard.writeText(targetEl.textContent);
        showToast('Copied to clipboard!');
      }
    });
  });

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

});
