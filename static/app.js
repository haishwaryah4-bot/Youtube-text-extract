// TubeAction AI - Core Client Application

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Lucide icons
  if (window.lucide) {
    lucide.createIcons();
  }

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

  // Chat Elements
  const chatForm = document.getElementById('chatForm');
  const chatInput = document.getElementById('chatInput');
  const chatMessages = document.getElementById('chatMessages');
  const chatChips = document.querySelectorAll('.chat-chip');

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

  // State
  let currentVideoId = null;
  let currentData = null;
  let timerInterval = null;
  let timerSeconds = 0;
  let chatHistory = [];
  let userApiKey = localStorage.getItem('tubeaction_openai_key') || '';

  if (apiKeyInput) {
    apiKeyInput.value = userApiKey;
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
    settingsModal.classList.add('hidden');
  });

  btnSaveSettings.addEventListener('click', () => {
    userApiKey = apiKeyInput.value.trim();
    localStorage.setItem('tubeaction_openai_key', userApiKey);
    settingsModal.classList.add('hidden');
    showToast(userApiKey ? 'OpenAI API key saved.' : 'Using default backend settings.');
  });

  // --- Tabs Switching ---
  tabButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetTab = btn.dataset.tab;
      switchTab(targetTab);
    });
  });

  function switchTab(tabId) {
    tabButtons.forEach((b) => b.classList.toggle('active', b.dataset.tab === tabId));
    tabPanes.forEach((p) => p.classList.toggle('active', p.id === tabId));
  }

  btnJumpPdfTab.addEventListener('click', () => switchTab('tab-pdf'));
  btnJumpChecklist.addEventListener('click', () => switchTab('tab-checklist'));

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

  async function processVideo(url) {
    errorSection.classList.add('hidden');
    resultsSection.classList.add('hidden');
    progressSection.classList.remove('hidden');
    btnProcess.disabled = true;

    startTimer();

    // Stage 1: URL Validation
    updateStepper(1, 'Validating YouTube URL...', 'Checking URL format and video availability');

    try {
      setTimeout(() => {
        if (!timerInterval) return;
        updateStepper(2, 'Fetching Transcript & Captions...', 'Retrieving authentic timestamped subtitles');
      }, 700);

      setTimeout(() => {
        if (!timerInterval) return;
        updateStepper(3, 'Processing Video Content...', 'Analyzing full transcript context with LangGraph');
      }, 1800);

      setTimeout(() => {
        if (!timerInterval) return;
        updateStepper(4, 'Generating Structured Summary...', 'Formulating overview & key points');
      }, 3000);

      setTimeout(() => {
        if (!timerInterval) return;
        updateStepper(5, 'Extracting Action Items...', 'Distinguishing demonstrated vs recommended instructions');
      }, 4200);

      setTimeout(() => {
        if (!timerInterval) return;
        updateStepper(6, 'Generating PDF Document...', 'Compiling professionally formatted report');
      }, 5500);

      // Call the standardized POST /api/youtube/analyze endpoint
      const response = await fetch('/api/youtube/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          youtube_url: url,
          api_key: userApiKey
        })
      });

      const data = await response.json();

      // Check if request or transcript retrieval failed
      if (!response.ok || !data.success || data.transcript_status !== 'success') {
        let userFacingError = data.error || 'Unable to process video.';
        if (data.transcript_status === 'rate_limited') {
          userFacingError = 'YouTube is temporarily rate-limiting automated transcript requests from this IP. Transcript analysis could not be completed.';
        } else if (data.transcript_status === 'captions_unavailable') {
          userFacingError = 'Captions or transcripts are disabled/unavailable for this video. Transcript analysis could not be performed.';
        } else if (data.transcript_status === 'video_unavailable') {
          userFacingError = 'This video is private, age-restricted, removed, or unavailable.';
        }

        throw new Error(userFacingError);
      }

      // Stage 7: Complete
      updateStepper(7, 'Complete!', 'All summary sections and PDF report ready.');
      setTimeout(() => {
        stopTimer();
        progressSection.classList.add('hidden');
        renderResults(data);
        btnProcess.disabled = false;
      }, 600);

    } catch (err) {
      stopTimer();
      progressSection.classList.add('hidden');
      errorSection.classList.remove('hidden');
      errorTitle.textContent = 'Transcript-Based Analysis Unavailable';
      errorMessage.textContent = err.message || 'An unexpected error occurred.';
      btnProcess.disabled = false;
      showToast(err.message);
    }
  }

  // --- Render Results ---
  function renderResults(data) {
    currentData = data;
    currentVideoId = data.video_id;
    chatHistory = [];

    // Header Video Details
    displayVideoTitle.textContent = data.title || 'YouTube Video';
    displayVideoAuthor.textContent = data.author || 'YouTube Creator';

    const demonstrated = data.demonstrated_actions || [];
    const recommended = data.recommended_actions || [];
    const allActions = [...demonstrated, ...recommended];

    badgeWordCount.innerHTML = `<i data-lucide="align-left" class="icon-xxs"></i> Verified (${data.transcript_status || 'success'})`;
    badgeActionCount.innerHTML = `<i data-lucide="check-square" class="icon-xxs"></i> ${allActions.length} Actions`;

    // Embed YouTube Player
    videoIframe.src = `https://www.youtube-nocookie.com/embed/${data.video_id}?enablejsapi=1`;

    // PDF links
    const pdfUrl = `/api/pdf/${data.video_id}`;
    const pdfDirectUrl = `${pdfUrl}?download=true`;
    btnDownloadPdf.href = pdfDirectUrl;
    btnPdfDownloadDirect.href = pdfDirectUrl;
    btnPdfOpenNewTab.href = pdfUrl;
    pdfIframe.src = pdfUrl;
    pdfFileName.textContent = `Report_${data.video_id}.pdf`;

    // Badges on tabs
    tabBadgeActions.textContent = allActions.length;
    tabBadgeChecklist.textContent = allActions.length;

    // 1. Render Summary Tab
    overviewContent.textContent = data.summary || 'Summary unavailable.';

    // Main Topics & Key Points
    mainTopicsList.innerHTML = '';
    const keyPoints = data.key_points || [];
    if (keyPoints.length > 0) {
      keyPoints.forEach((point, idx) => {
        const card = document.createElement('div');
        card.className = 'topic-card';
        card.innerHTML = `
          <div class="topic-title">Key Insight ${idx + 1}</div>
          <div class="topic-desc">${escapeHtml(point)}</div>
        `;
        mainTopicsList.appendChild(card);
      });
    }

    renderListItems(factsList, data.key_points || []);
    renderListItems(explanationsList, data.tools_materials || []);
    renderListItems(recommendationsList, data.precautions || []);

    // Update headings for facts/explanations/recommendations columns if appropriate
    const factsHeader = factsList.parentElement.querySelector('h4');
    if (factsHeader) factsHeader.textContent = 'Key Points';
    const toolsHeader = explanationsList.parentElement.querySelector('h4');
    if (toolsHeader) toolsHeader.textContent = 'Tools & Materials Mentioned';
    const precHeader = recommendationsList.parentElement.querySelector('h4');
    if (precHeader) precHeader.textContent = 'Precautions & Warnings';

    finalSummaryContent.textContent = data.summary || 'Grounded video summary complete.';

    // 2. Render Actions Tab
    renderActions(demonstrated, recommended);

    // 3. Render Checklist Tab
    const checklistItems = allActions.map(a => a.name || a.description || 'Action Item');
    renderChecklist(checklistItems, data.video_id);

    // 4. Render Raw Transcript if present
    renderTranscript(data.raw_transcript || '');

    // Reset Chat Box
    chatMessages.innerHTML = `
      <div class="message bot-message">
        <div class="message-bubble">
          I'm ready! I have analyzed the verified transcript for <b>"${escapeHtml(data.title)}"</b>. Ask me anything about the instructions, specific details, or concepts discussed!
        </div>
      </div>
    `;

    resultsSection.classList.remove('hidden');
    switchTab('tab-summary');

    if (window.lucide) {
      lucide.createIcons();
    }
  }

  function renderListItems(container, items) {
    container.innerHTML = '';
    if (!items || items.length === 0) {
      container.innerHTML = `<li class="text-dim">None mentioned.</li>`;
      return;
    }
    items.forEach((item) => {
      const li = document.createElement('li');
      li.textContent = item;
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
            ${steps.map((s, sIdx) => `
              <div class="step-item">
                <div class="step-badge-num">${sIdx + 1}</div>
                <div class="step-item-text">${escapeHtml(s)}</div>
              </div>
            `).join('')}
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
          if (videoIframe && currentVideoId) {
            videoIframe.src = `https://www.youtube-nocookie.com/embed/${currentVideoId}?autoplay=1&start=${totalSecs}`;
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

  // --- Grounded AI Chat ---
  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = chatInput.value.trim();
    if (!msg || !currentVideoId) return;

    appendChatMessage('user', msg);
    chatInput.value = '';

    // Bot Typing Placeholder
    const botLoadingBubble = appendChatMessage('bot', 'Thinking...', true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_id: currentVideoId,
          message: msg,
          history: chatHistory,
          api_key: userApiKey
        })
      });

      const data = await res.json();
      botLoadingBubble.innerHTML = escapeHtml(data.reply || 'No answer available.');
      chatHistory.push({ role: 'user', content: msg });
      chatHistory.push({ role: 'assistant', content: data.reply });
    } catch (err) {
      botLoadingBubble.innerHTML = 'Error communicating with assistant. Please try again.';
    }
  });

  chatChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      chatInput.value = chip.dataset.msg;
      chatForm.dispatchEvent(new Event('submit'));
    });
  });

  function appendChatMessage(role, text, isLoading = false) {
    const msgEl = document.createElement('div');
    msgEl.className = `message ${role}-message`;
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = text;
    msgEl.appendChild(bubble);
    chatMessages.appendChild(msgEl);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return bubble;
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
