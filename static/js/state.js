window.F1_STATE = {
    activeTab: "predict",
    selectedRaceCode: null,
    timers: {
        speed: null,
        location: null,
        liveHeavy: null,
        tyres: null,
        strategy: null,
        practice: null,
        trackShape: null,
    },
    streams: {
        speed: null,
        location: null,
        practice: null,
    },
    lastGood: {
        liveTiming: null,
        speed: null,
        location: null,
        tyres: null,
        strategyTimeline: null,
        pitPredictor: null,
        practice: null,
        trackShape: null,
    }
};

function clearTimer(name) {
    const id = F1_STATE.timers[name];
    if (id) {
        clearInterval(id);
        F1_STATE.timers[name] = null;
    }
}

function closeStream(name) {
    const stream = F1_STATE.streams[name];
    if (stream) {
        stream.close();
        F1_STATE.streams[name] = null;
    }
}

function stopAllLiveProcesses() {
    Object.keys(F1_STATE.timers).forEach(clearTimer);
    Object.keys(F1_STATE.streams).forEach(closeStream);
}
