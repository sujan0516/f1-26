async function apiGet(path) {
    const res = await fetch(path, {
        headers: { "Accept": "application/json" }
    });

    const contentType = res.headers.get("content-type") || "";

    if (!res.ok) {
        let msg = `${res.status} ${res.statusText}`;

        if (contentType.includes("application/json")) {
            try {
                const data = await res.json();
                msg = data.error || data.message || msg;
            } catch (e) {}
        }

        throw new Error(msg);
    }

    if (!contentType.includes("application/json")) {
        throw new Error(`Expected JSON but received ${contentType || "unknown content type"}`);
    }

    return await res.json();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
