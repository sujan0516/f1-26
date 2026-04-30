function switchTab(tabId) {
    // 1. Clean up all active streams and timers from the previous tab
    stopAllLiveProcesses();
    
    // 2. Update UI State
    const tabs = document.querySelectorAll('.nav-btn');
    const panels = document.querySelectorAll('.panel');
    
    tabs.forEach(t => t.classList.remove('active'));
    panels.forEach(p => p.classList.remove('active'));
    
    const activeBtn = document.querySelector(`.nav-btn[onclick*="${tabId}"]`);
    const activePanel = document.getElementById(`panel-${tabId}`);
    
    if (activeBtn) activeBtn.classList.add('active');
    if (activePanel) activePanel.classList.add('active');
    
    F1_STATE.activeTab = tabId;
    
    // 3. Initialize the new tab's specific logic
    initializeTab(tabId);
}

function initializeTab(tabId) {
    console.log(`Initializing Tab: ${tabId}`);
    
    if (tabId === 'live') {
        loadTrackShape();
        startLiveTimingLoops();
    } else if (tabId === 'strategy') {
        loadRaceStrategy();
    } else if (tabId === 'tyres') {
        loadTyres();
    } else if (tabId === 'practice') {
        loadPractice();
    }
}

function startLiveTimingLoops() {
    // Speed: 1 second (Phase 16)
    F1_STATE.timers.speed = setInterval(fetchSpeed, 1000);
    
    // Location: 2 seconds
    F1_STATE.timers.location = setInterval(fetchLocation, 2000);
    
    // Heavy Timing: 5-10 seconds
    F1_STATE.timers.liveHeavy = setInterval(fetchHeavyTiming, 7000);
}
