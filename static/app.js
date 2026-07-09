// Guarde Clipboard Parser - Core Frontend Logic
document.addEventListener("DOMContentLoaded", () => {
    // State Variables
    let labels = []; // [{name, start, end, text}]
    let currentSelection = null;
    let eventSource = null;
    let activeProviderId = null;
    let savedProviders = [];
    let lastProcessedClipboard = "";

    // Cached DOM Elements
    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("status-text");
    const activeProviderBadge = document.getElementById("active-provider-badge");
    const consoleLogFeed = document.getElementById("console-log-feed");
    const clearLogsBtn = document.getElementById("clear-logs");
    
    // Tab Elements
    const navTabs = document.querySelectorAll(".nav-tab");
    const tabContents = document.querySelectorAll(".tab-content");
    
    // Tab 1 Elements
    const monitorToggle = document.getElementById("monitor-toggle");
    const providerSelect = document.getElementById("provider-select");
    const lastCaptureContainer = document.getElementById("last-capture-container");
    const recentCapturesHeaders = document.getElementById("recent-captures-headers");
    const recentCapturesBody = document.getElementById("recent-captures-body");
    const btnDownloadRaw = document.getElementById("btn-download-raw");
    const btnClearCaptures = document.getElementById("btn-clear-captures");
    const btnPasteClipboard = document.getElementById("btn-paste-clipboard");
    const pasteInputArea = document.getElementById("paste-input-area");
    
    // Tab 2 Elements
    const provNameInput = document.getElementById("prov-name");
    const provIdInput = document.getElementById("prov-id");
    const provFormatSelect = document.getElementById("prov-format");
    const rawTrainText = document.getElementById("raw-train-text");
    const labelingWorkspace = document.getElementById("labeling-workspace-container");
    const interactiveTextBox = document.getElementById("interactive-text-box");
    const activeTagsSection = document.getElementById("active-tags-section");
    const tagsBadgeContainer = document.getElementById("tags-badge-container");
    const btnGenerateRegex = document.getElementById("btn-generate-regex");
    const btnSaveProvider = document.getElementById("btn-save-provider");
    const regexResultsCard = document.getElementById("regex-results-card");
    const generatedRegexString = document.getElementById("generated-regex-string");
    const regexMatchStatus = document.getElementById("regex-match-status");
    const extractedFieldsJson = document.getElementById("extracted-fields-json");
    const savedProvidersList = document.getElementById("saved-providers-list");
    const clearSelectionsBtn = document.getElementById("clear-selections");
    const tagButtons = document.querySelectorAll(".tag-btn[data-tag]");
    
    // Tab 3 Elements
    const filesChecklist = document.getElementById("files-checklist");
    const mergeKeySelect = document.getElementById("merge-key");
    const mergeOutputInput = document.getElementById("merge-output");
    const btnRunMerge = document.getElementById("btn-run-merge");
    const mergedResultsCard = document.getElementById("merged-results-card");
    const mergedResultsHeaders = document.getElementById("merged-results-headers");
    const mergedResultsBody = document.getElementById("merged-results-body");
    const btnDownloadConsolidated = document.getElementById("btn-download-consolidated");
    const btnClearMerged = document.getElementById("btn-clear-merged");
    const uploadZone = document.getElementById("upload-zone");
    const uploadInput = document.getElementById("upload-input");

    // Tab 4 Elements (Root Only)
    const tabUsersBtn = document.getElementById("tab-users-btn");
    const newUsernameInput = document.getElementById("new-username");
    const newPasswordInput = document.getElementById("new-password");
    const btnCreateUser = document.getElementById("btn-create-user");
    const registeredUsersList = document.getElementById("registered-users-list");
    const authWarningBox = document.getElementById("auth-warning-box");

    // ----------------------------------------------------
    // 1. TABS MANAGEMENT
    // ----------------------------------------------------
    navTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            navTabs.forEach(t => t.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            
            tab.classList.add("active");
            const targetContent = document.getElementById(tab.dataset.tab);
            targetContent.classList.add("active");

            // Custom actions when switching tabs
            if (tab.dataset.tab === "tab-merge") {
                loadExtractionFiles();
            } else if (tab.dataset.tab === "tab-train") {
                loadProviders();
            } else if (tab.dataset.tab === "tab-users") {
                loadRegisteredUsers();
            } else if (tab.dataset.tab === "tab-stock") {
                loadStockMatrix();
            }
        });
    });

    // Auto-generate ID from Name
    provNameInput.addEventListener("input", () => {
        if (!provIdInput.value || provIdInput.dataset.autogen !== "false") {
            provIdInput.value = provNameInput.value
                .toLowerCase()
                .trim()
                .replace(/[^a-z0-9_]/g, "_")
                .replace(/_+/g, "_");
            provIdInput.dataset.autogen = "true";
        }
    });

    provIdInput.addEventListener("focus", () => {
        provIdInput.dataset.autogen = "false";
    });

    // ----------------------------------------------------
    // 2. REAL-TIME LOGGING & DAEMON CONNECTION (SSE)
    // ----------------------------------------------------
    function initSSEConnection() {
        if (eventSource) {
            eventSource.close();
        }
        
        eventSource = new EventSource("/api/stream");
        
        eventSource.onopen = () => {
            statusDot.className = "dot online";
            statusText.textContent = "Servicio Activo";
        };
        
        eventSource.onerror = () => {
            statusDot.className = "dot offline";
            statusText.textContent = "Desconectado";
        };
        
        eventSource.addEventListener("message", (e) => {
            const data = JSON.parse(e.data);
            
            if (data.type === "init") {
                consoleLogFeed.innerHTML = "";
                data.logs.forEach(log => appendLog(log));
            } else if (data.type === "log") {
                appendLog(data.log);
                if (data.log.type === "success" && data.log.data) {
                    displayLastCapture(data.log.data);
                    loadRecentCaptures();
                }
            }
        });
    }

    function appendLog(log) {
        const logEntry = document.createElement("div");
        logEntry.className = "log-entry";
        
        const timeSpan = document.createElement("span");
        timeSpan.className = "log-time";
        timeSpan.textContent = `[${log.timestamp}]`;
        
        const msgSpan = document.createElement("span");
        msgSpan.className = `log-msg log-${log.type}`;
        msgSpan.textContent = log.message;
        
        logEntry.appendChild(timeSpan);
        logEntry.appendChild(msgSpan);
        consoleLogFeed.appendChild(logEntry);
        consoleLogFeed.scrollTop = consoleLogFeed.scrollHeight;
    }

    clearLogsBtn.addEventListener("click", () => {
        consoleLogFeed.innerHTML = "";
    });

    // ----------------------------------------------------
    // 3. MONITOR CONTROLS & RECENT TABLES
    // ----------------------------------------------------
    async function loadStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();
            
            monitorToggle.checked = data.is_monitoring;
            activeProviderId = data.active_provider ? data.active_provider.id : null;
            
            updateActiveBadge(data.active_provider);
            await loadProviders();
            
            if (activeProviderId) {
                providerSelect.value = activeProviderId;
                loadRecentCaptures();
            } else {
                providerSelect.value = "";
                showEmptyRecentTable();
            }

            // Actualizar la interfaz de usuario en base a los privilegios
            if (data.is_root) {
                tabUsersBtn.style.display = "inline-block";
                authWarningBox.style.display = data.auth_enabled ? "none" : "block";
            } else {
                tabUsersBtn.style.display = "none";
            }
        } catch (err) {
            console.error("Error cargando estado:", err);
        }
    }

    function updateActiveBadge(provider) {
        if (provider) {
            activeProviderBadge.textContent = `Proveedor: ${provider.name}`;
            activeProviderBadge.style.backgroundColor = "rgba(108, 92, 231, 0.15)";
            activeProviderBadge.style.borderColor = "var(--primary)";
        } else {
            activeProviderBadge.textContent = "Proveedor: Ninguno (Inactivo)";
            activeProviderBadge.style.backgroundColor = "rgba(255, 255, 255, 0.05)";
            activeProviderBadge.style.borderColor = "var(--border-color)";
        }
    }

    monitorToggle.addEventListener("change", async () => {
        try {
            const res = await fetch("/api/status/toggle", { method: "POST" });
            const data = await res.json();
            monitorToggle.checked = data.is_monitoring;
        } catch (err) {
            console.error("Error al alternar monitoreo:", err);
        }
    });

    providerSelect.addEventListener("change", async () => {
        const val = providerSelect.value || null;
        try {
            const res = await fetch("/api/providers/select", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ provider_id: val })
            });
            const data = await res.json();
            activeProviderId = data.active_provider ? data.active_provider.id : null;
            updateActiveBadge(data.active_provider);
            loadStatus();
            lastProcessedClipboard = ""; // Reset duplicate detection on provider change
        } catch (err) {
            console.error("Error al cambiar proveedor:", err);
        }
    });

    function displayLastCapture(data) {
        lastCaptureContainer.className = "capture-card";
        lastCaptureContainer.innerHTML = "";
        
        Object.entries(data).forEach(([key, val]) => {
            if (key === "timestamp") return;
            const row = document.createElement("div");
            row.className = "capture-item";
            
            const keySpan = document.createElement("span");
            keySpan.className = "capture-key";
            keySpan.textContent = translateKey(key);
            
            const valSpan = document.createElement("span");
            valSpan.className = "capture-val";
            valSpan.textContent = val;
            
            row.appendChild(keySpan);
            row.appendChild(valSpan);
            lastCaptureContainer.appendChild(row);
        });
        
        const timeRow = document.createElement("div");
        timeRow.className = "capture-item mt-10";
        timeRow.style.fontSize = "11px";
        timeRow.style.color = "var(--text-muted)";
        timeRow.textContent = `Capturado a las ${data.timestamp}`;
        lastCaptureContainer.appendChild(timeRow);
    }

    function translateKey(key) {
        const mappings = {
            "product": "Producto",
            "producto": "Producto",
            "model": "Modelo / SKU",
            "modelo": "Modelo / SKU",
            "price": "Precio",
            "precio": "Precio",
            "price_no_vat": "Precio Sin IVA",
            "precio_sin_iva": "Precio Sin IVA",
            "price_vat": "Precio Con IVA",
            "precio_con_iva": "Precio Con IVA",
            "pvp": "PVP",
            "precio_pvp": "PVP",
            "attributes": "Atributos Técnicos",
            "atributos": "Atributos Técnicos"
        };
        return mappings[key] || key;
    }    async function loadRecentCaptures() {
        if (!activeProviderId) {
            showEmptyRecentTable();
            return;
        }
        
        btnDownloadRaw.href = `/api/extractions/download/${activeProviderId}`;
        btnDownloadRaw.style.display = "inline-block";
        btnClearCaptures.style.display = "inline-block";
        
        const provider = savedProviders.find(p => p.id === activeProviderId);
        if (!provider) return;
        
        const ext = provider.file_format || "csv";
        btnDownloadRaw.setAttribute("download", `${provider.id}.${ext}`);
        
        try {
            const res = await fetch(`/api/providers/${activeProviderId}/data`);
            if (!res.ok) {
                recentCapturesBody.innerHTML = `<tr><td class="table-empty" colspan="100%">El archivo de extracción aún no existe. Comienza a copiar datos para crearlo.</td></tr>`;
                recentCapturesHeaders.innerHTML = `<th>Producto / Modelo</th><th>Precio</th><th>Atributos</th><th>Fecha</th><th>Acciones</th>`;
                btnClearCaptures.style.display = "none";
                btnDownloadRaw.style.display = "none";
                return;
            }
            const data = await res.json();
            
            if (data.columns && data.columns.length > 0) {
                // Render headers
                recentCapturesHeaders.innerHTML = "";
                data.columns.forEach(col => {
                    if (col.toLowerCase() === 'pvp' || col.toLowerCase() === 'precio_pvp') return;
                    const th = document.createElement("th");
                    th.textContent = translateKey(col);
                    recentCapturesHeaders.appendChild(th);
                });
                
                // Header de acciones
                const thActions = document.createElement("th");
                thActions.textContent = "Acciones";
                thActions.style.textAlign = "center";
                recentCapturesHeaders.appendChild(thActions);
                
                // Render body
                recentCapturesBody.innerHTML = "";
                if (data.records.length === 0) {
                    recentCapturesBody.innerHTML = `<tr><td class="table-empty" colspan="100%">No hay registros en este archivo.</td></tr>`;
                    btnClearCaptures.style.display = "none";
                    btnDownloadRaw.style.display = "none";
                } else {
                    // Mostrar los últimos 50 de forma invertida (más reciente primero)
                    const displayData = data.records.slice(-50).reverse();
                    displayData.forEach(row => {
                        const tr = document.createElement("tr");
                        data.columns.forEach(col => {
                            if (col.toLowerCase() === 'pvp' || col.toLowerCase() === 'precio_pvp') return;
                            const td = document.createElement("td");
                            td.textContent = row[col] !== null ? row[col] : "";
                            tr.appendChild(td);
                        });
                        
                        // Celda de acciones con botón de borrado individual
                        const tdAction = document.createElement("td");
                        tdAction.style.textAlign = "center";
                        
                        const btnDel = document.createElement("button");
                        btnDel.className = "btn-delete-row";
                        btnDel.innerHTML = "🗑️";
                        btnDel.title = "Borrar esta captura";
                        btnDel.onclick = async () => {
                            if (confirm("¿Estás seguro de que deseas eliminar esta captura específica?")) {
                                await deleteCaptureRow(row._index);
                            }
                        };
                        
                        tdAction.appendChild(btnDel);
                        tr.appendChild(tdAction);
                        recentCapturesBody.appendChild(tr);
                    });
                }
            } else {
                showEmptyRecentTable();
            }
        } catch (err) {
            console.error("Error al cargar capturas recientes:", err);
            showEmptyRecentTable();
        }
    }
 
    function showEmptyRecentTable() {
        recentCapturesHeaders.innerHTML = `<th>Producto / Modelo</th><th>Precio</th><th>Atributos</th><th>Fecha</th><th>Acciones</th>`;
        recentCapturesBody.innerHTML = `<tr><td class="table-empty" colspan="100%">Selecciona un proveedor activo para visualizar sus capturas locales.</td></tr>`;
        btnDownloadRaw.style.display = "none";
        btnClearCaptures.style.display = "none";
    }

    async function deleteCaptureRow(index) {
        try {
            const res = await fetch(`/api/providers/${activeProviderId}/delete-row`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ index: index })
            });
            if (res.ok) {
                loadRecentCaptures();
            } else {
                alert("Error al intentar eliminar la captura.");
            }
        } catch (err) {
            console.error("Error eliminando captura:", err);
        }
    }

    btnClearCaptures.addEventListener("click", async () => {
        if (!activeProviderId) return;
        if (confirm("¿Estás seguro de que deseas vaciar y eliminar todas las capturas de este proveedor? Esta acción no se puede deshacer.")) {
            try {
                const res = await fetch(`/api/providers/${activeProviderId}/clear`, {
                    method: "POST"
                });
                if (res.ok) {
                    loadRecentCaptures();
                } else {
                    alert("Error al intentar limpiar las capturas.");
                }
            } catch (err) {
                console.error("Error limpiando capturas:", err);
            }
        }
    });

    // ----------------------------------------------------
    // 4. NO-CODE REGEX TRAINING & ASSISTANT
    // ----------------------------------------------------
    async function loadProviders() {
        try {
            const res = await fetch("/api/providers");
            const data = await res.json();
            savedProviders = data.providers || [];
            
            // Popular sidebar
            savedProvidersList.innerHTML = "";
            if (savedProviders.length === 0) {
                savedProvidersList.innerHTML = `<p class="empty-text">No hay plantillas guardadas.</p>`;
            } else {
                savedProviders.forEach(p => {
                    const item = document.createElement("div");
                    item.className = `provider-item ${p.id === activeProviderId ? 'active' : ''}`;
                    item.onclick = () => loadProviderIntoTrainer(p);
                    
                    const info = document.createElement("div");
                    info.className = "provider-info";
                    
                    const h4 = document.createElement("h4");
                    h4.textContent = p.name;
                    
                    const pSpan = document.createElement("p");
                    pSpan.textContent = `Campos: ${p.fields.join(", ")} (${p.file_format.toUpperCase()})`;
                    
                    info.appendChild(h4);
                    info.appendChild(pSpan);
                    
                    const deleteBtn = document.createElement("button");
                    deleteBtn.className = "btn-delete-prov";
                    deleteBtn.innerHTML = "🗑️";
                    deleteBtn.title = "Eliminar plantilla";
                    deleteBtn.onclick = (e) => {
                        e.stopPropagation();
                        deleteProvider(p.id);
                    };
                    
                    item.appendChild(info);
                    item.appendChild(deleteBtn);
                    savedProvidersList.appendChild(item);
                });
            }
            
            // Popular selector
            const currentVal = providerSelect.value;
            providerSelect.innerHTML = `<option value="">-- Seleccionar Proveedor --</option>`;
            savedProviders.forEach(p => {
                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = p.name;
                providerSelect.appendChild(opt);
            });
            if (currentVal && savedProviders.some(p => p.id === currentVal)) {
                providerSelect.value = currentVal;
            }
        } catch (err) {
            console.error("Error al cargar proveedores:", err);
        }
    }

    function loadProviderIntoTrainer(p) {
        provNameInput.value = p.name;
        provIdInput.value = p.id;
        provIdInput.dataset.autogen = "false";
        provFormatSelect.value = p.file_format;
        rawTrainText.value = p.sample_text;
        labels = [...p.labels];
        
        // Disparar renderizado del workspace
        labelingWorkspace.style.display = "block";
        activeTagsSection.style.display = "block";
        renderInteractiveText();
        btnSaveProvider.disabled = false;
        
        // Simular clic en el test
        generateAndTestRegex();
    }

    async function deleteProvider(id) {
        if (!confirm(`¿Seguro que deseas eliminar la plantilla del proveedor '${id}'?`)) return;
        try {
            await fetch(`/api/providers/${id}`, { method: "DELETE" });
            if (activeProviderId === id) activeProviderId = null;
            loadStatus();
        } catch (err) {
            console.error("Error al eliminar proveedor:", err);
        }
    }

    rawTrainText.addEventListener("input", () => {
        const text = rawTrainText.value;
        if (text) {
            labelingWorkspace.style.display = "block";
            activeTagsSection.style.display = "block";
            labels = []; // Limpiar etiquetas anteriores
            renderInteractiveText();
        } else {
            labelingWorkspace.style.display = "none";
            activeTagsSection.style.display = "none";
            regexResultsCard.style.display = "none";
            btnSaveProvider.disabled = true;
        }
    });

    // Highlighter logic
    interactiveTextBox.addEventListener("mouseup", () => {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        if (!selectedText) return;
        
        const startOffset = getSelectionCharacterOffsetWithin(interactiveTextBox);
        const endOffset = startOffset + selectedText.length;
        
        // Guardar selección temporal
        currentSelection = {
            text: selectedText,
            start: startOffset,
            end: endOffset
        };
    });

    function getSelectionCharacterOffsetWithin(element) {
        let start = 0;
        const doc = element.ownerDocument || element.document;
        const win = doc.defaultView || doc.parentWindow;
        let sel;
        if (typeof win.getSelection != "undefined") {
            sel = win.getSelection();
            if (sel.rangeCount > 0) {
                const range = win.getSelection().getRangeAt(0);
                const preCaretRange = range.cloneRange();
                preCaretRange.selectNodeContents(element);
                preCaretRange.setEnd(range.startContainer, range.startOffset);
                start = preCaretRange.toString().length;
            }
        }
        return start;
    }

    tagButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const tagName = btn.dataset.tag;
            const existingIndex = labels.findIndex(l => l.name === tagName);
            
            if (!currentSelection) {
                if (existingIndex !== -1) {
                    // Si ya existe la etiqueta y le volvemos a dar al botón, se borra lo señalado
                    labels.splice(existingIndex, 1);
                    renderInteractiveText();
                    window.getSelection().removeAllRanges();
                } else {
                    alert("Primero selecciona/sombrea un fragmento de texto en la caja.");
                }
                return;
            }
            
            // Si hay una selección activa y ya existía esta etiqueta, la removemos primero para reemplazarla
            if (existingIndex !== -1) {
                labels.splice(existingIndex, 1);
            }
            
            // Validar que no se solape
            const overlap = labels.some(l => 
                (currentSelection.start >= l.start && currentSelection.start < l.end) ||
                (currentSelection.end > l.start && currentSelection.end <= l.end) ||
                (l.start >= currentSelection.start && l.start < currentSelection.end)
            );
            
            if (overlap) {
                alert("La selección se solapa con una etiqueta existente.");
                return;
            }
            
            labels.push({
                name: tagName,
                start: currentSelection.start,
                end: currentSelection.end,
                text: currentSelection.text
            });
            
            // Limpiar selección del navegador
            window.getSelection().removeAllRanges();
            currentSelection = null;
            
            renderInteractiveText();
        });
    });

    clearSelectionsBtn.addEventListener("click", () => {
        labels = [];
        currentSelection = null;
        renderInteractiveText();
        regexResultsCard.style.display = "none";
        btnSaveProvider.disabled = true;
    });

    function renderInteractiveText() {
        const rawText = rawTrainText.value;
        if (!rawText) return;
        
        const sorted = [...labels].sort((a, b) => a.start - b.start);
        
        let html = "";
        let lastIdx = 0;
        
        sorted.forEach(l => {
            html += escapeHtml(rawText.substring(lastIdx, l.start));
            html += `<span class="tagged-span tagged-${l.name}">${escapeHtml(rawText.substring(l.start, l.end))}</span>`;
            lastIdx = l.end;
        });
        html += escapeHtml(rawText.substring(lastIdx));
        
        interactiveTextBox.innerHTML = html;
        renderTagsBadges();
    }

    function renderTagsBadges() {
        tagsBadgeContainer.innerHTML = "";
        if (labels.length === 0) {
            tagsBadgeContainer.innerHTML = `<span style="font-size:12px; color:var(--text-muted);">Sin etiquetas asignadas</span>`;
            return;
        }
        
        labels.forEach((l, idx) => {
            const badge = document.createElement("span");
            badge.className = `tag-badge badge-${l.name}`;
            badge.innerHTML = `${translateKey(l.name)}: "<strong>${escapeHtml(l.text)}</strong>"`;
            
            const removeBtn = document.createElement("button");
            removeBtn.className = "btn-remove-tag";
            removeBtn.textContent = "×";
            removeBtn.onclick = () => {
                labels.splice(idx, 1);
                renderInteractiveText();
            };
            
            badge.appendChild(removeBtn);
            tagsBadgeContainer.appendChild(badge);
        });
    }

    function escapeHtml(text) {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    btnGenerateRegex.addEventListener("click", generateAndTestRegex);

    async function generateAndTestRegex() {
        if (labels.length === 0) {
            alert("Asigna al menos una etiqueta para poder entrenar el Regex.");
            return;
        }
        
        try {
            const res = await fetch("/api/regex/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    raw_text: rawTrainText.value,
                    labels: labels
                })
            });
            const data = await res.json();
            
            regexResultsCard.style.display = "block";
            generatedRegexString.textContent = data.regex;
            
            if (data.status === "success") {
                regexMatchStatus.className = "regex-match-status status-box-success";
                regexMatchStatus.textContent = "✓ ¡Éxito! La expresión regular coincide perfectamente con el texto de muestra.";
                extractedFieldsJson.textContent = JSON.stringify(data.extracted, null, 2);
                btnSaveProvider.disabled = false;
            } else if (data.status === "warning") {
                regexMatchStatus.className = "regex-match-status status-box-warning";
                regexMatchStatus.textContent = `⚠ Advertencia: ${data.message}`;
                extractedFieldsJson.textContent = "{}";
                btnSaveProvider.disabled = true;
            } else {
                regexMatchStatus.className = "regex-match-status status-box-error";
                regexMatchStatus.textContent = `✗ Error: ${data.message}`;
                extractedFieldsJson.textContent = "{}";
                btnSaveProvider.disabled = true;
            }
        } catch (err) {
            console.error("Error al generar regex:", err);
            alert("Ocurrió un error al contactar al backend.");
        }
    }

    btnSaveProvider.addEventListener("click", async () => {
        const id = provIdInput.value.trim();
        const name = provNameInput.value.trim();
        const format = provFormatSelect.value;
        const regex = generatedRegexString.textContent;
        const rawText = rawTrainText.value;
        
        if (!id || !name) {
            alert("Introduce un Nombre e ID válido para el proveedor.");
            return;
        }
        
        const fields = labels.map(l => l.name);
        const output_file = `data/extractions/${id}.${format}`;
        
        const providerData = {
            id: id,
            name: name,
            regex: regex,
            fields: fields,
            output_file: output_file,
            file_format: format,
            sample_text: rawText,
            labels: labels
        };
        
        try {
            const res = await fetch("/api/providers", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(providerData)
            });
            if (res.ok) {
                alert("¡Plantilla del proveedor guardada exitosamente!");
                
                // Limpiar formulario
                provNameInput.value = "";
                provIdInput.value = "";
                provIdInput.dataset.autogen = "true";
                rawTrainText.value = "";
                labels = [];
                currentSelection = null;
                
                labelingWorkspace.style.display = "none";
                activeTagsSection.style.display = "none";
                regexResultsCard.style.display = "none";
                btnSaveProvider.disabled = true;
                
                loadStatus();
            } else {
                alert("Error al guardar la plantilla en el servidor.");
            }
        } catch (err) {
            console.error("Error guardando proveedor:", err);
        }
    });

    // ----------------------------------------------------
    // 5. FUSIÓN COMERCIAL & COMPARADOR (TAB 3)
    // ----------------------------------------------------
    async function loadExtractionFiles() {
        try {
            const res = await fetch("/api/extractions/files");
            const files = await res.json();
            
            filesChecklist.innerHTML = "";
            if (files.length === 0) {
                filesChecklist.innerHTML = `<p class="empty-text">No hay archivos en 'data/extractions'. Captura algunos datos primero.</p>`;
                return;
            }
            
            files.forEach(f => {
                const label = document.createElement("label");
                label.className = "file-check-item";
                
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.value = f.filename;
                checkbox.name = "extraction-files";
                
                const span = document.createElement("span");
                span.textContent = f.filename;
                
                const info = document.createElement("span");
                info.className = "file-info-sub";
                info.textContent = `(${formatBytes(f.size)} - modificado: ${f.last_modified})`;
                
                const deleteBtn = document.createElement("button");
                deleteBtn.type = "button";
                deleteBtn.className = "btn-delete-file";
                deleteBtn.innerHTML = "🗑️";
                deleteBtn.title = "Eliminar este archivo";
                deleteBtn.addEventListener("click", async (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (confirm(`¿Estás seguro de que deseas eliminar permanentemente el archivo ${f.filename}?`)) {
                        await deleteExtractionFile(f.filename);
                    }
                });
                
                label.appendChild(checkbox);
                label.appendChild(span);
                label.appendChild(info);
                label.appendChild(deleteBtn);
                filesChecklist.appendChild(label);
            });
        } catch (err) {
            console.error("Error al cargar archivos:", err);
        }
    }

    async function deleteExtractionFile(filename) {
        try {
            const res = await fetch(`/api/extractions/files/${encodeURIComponent(filename)}`, {
                method: "DELETE"
            });
            if (res.ok) {
                loadExtractionFiles();
            } else {
                const errData = await res.json();
                alert(`Error al eliminar el archivo: ${errData.detail || "Error interno"}`);
            }
        } catch (err) {
            console.error("Error al eliminar el archivo:", err);
            alert("Error de conexión al eliminar el archivo.");
        }
    }

    function formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    btnRunMerge.addEventListener("click", async () => {
        const checkboxes = document.querySelectorAll("input[name='extraction-files']:checked");
        if (checkboxes.length === 0) {
            alert("Selecciona al menos un archivo de la lista.");
            return;
        }
        
        const files = Array.from(checkboxes).map(c => c.value);
        const mergeKey = mergeKeySelect.value;
        const outFilename = mergeOutputInput.value.trim() || "comparativa_precios.xlsx";
        
        try {
            btnRunMerge.disabled = true;
            btnRunMerge.textContent = "⚡ Fusionando...";
            
            const res = await fetch("/api/extractions/merge", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    files: files,
                    merge_key: mergeKey,
                    output_filename: outFilename
                })
            });
            
            if (!res.ok) {
                const errData = await res.json();
                alert(`Error en la fusión: ${errData.detail || "Error interno"}`);
                return;
            }
            
            const data = await res.json();
            displayMergeResults(data);
        } catch (err) {
            console.error("Error de fusión:", err);
            alert("Error de conexión al fusionar.");
        } finally {
            btnRunMerge.disabled = false;
            btnRunMerge.textContent = "⚡ Unificar Tablas y Comparar Precios";
        }
    });

    function displayMergeResults(result) {
        mergedResultsCard.style.display = "block";
        btnDownloadConsolidated.href = `/api/consolidated/download/${result.file}`;
        btnDownloadConsolidated.setAttribute("download", result.file);
        
        // Render headers
        mergedResultsHeaders.innerHTML = "";
        result.columns.forEach(col => {
            if (col.toLowerCase().includes('pvp')) return;
            const th = document.createElement("th");
            th.textContent = col;
            mergedResultsHeaders.appendChild(th);
        });
        
        // Render body
        mergedResultsBody.innerHTML = "";
        if (result.data.length === 0) {
            mergedResultsBody.innerHTML = `<tr><td class="table-empty" colspan="100%">No se generaron registros tras la unificación.</td></tr>`;
            return;
        }
        
        result.data.forEach(row => {
            const tr = document.createElement("tr");
            
            // Determinar los precios mínimos independientes por cada categoría de precio
            let minGeneral = Infinity;
            let generalCols = [];
            let minNoVat = Infinity;
            let noVatCols = [];
            let minVat = Infinity;
            let vatCols = [];
            
            result.columns.forEach(col => {
                if (col.startsWith("Precio ")) {
                    const val = parseFloat(row[col]);
                    if (!isNaN(val) && val > 0) {
                        if (col.endsWith(" Sin IVA (€)")) {
                            noVatCols.push(col);
                            if (val < minNoVat) minNoVat = val;
                        } else if (col.endsWith(" Con IVA (€)")) {
                            vatCols.push(col);
                            if (val < minVat) minVat = val;
                        } else if (col.endsWith(" (€)")) {
                            generalCols.push(col);
                            if (val < minGeneral) minGeneral = val;
                        }
                    }
                }
            });
            
            result.columns.forEach(col => {
                if (col.toLowerCase().includes('pvp')) return;
                const td = document.createElement("td");
                const val = row[col];
                td.textContent = val !== null ? val : "";
                
                // Destacar precio mínimo en base a su grupo
                if (col.startsWith("Precio ")) {
                    const priceVal = parseFloat(val);
                    if (!isNaN(priceVal) && priceVal > 0) {
                        if (col.endsWith(" Sin IVA (€)") && priceVal === minNoVat && noVatCols.length > 1) {
                            td.className = "highlight-cheap";
                        } else if (col.endsWith(" Con IVA (€)") && priceVal === minVat && vatCols.length > 1) {
                            td.className = "highlight-cheap";
                        } else if (col.endsWith(" (€)") && !col.endsWith(" Sin IVA (€)") && !col.endsWith(" Con IVA (€)") && priceVal === minGeneral && generalCols.length > 1) {
                            td.className = "highlight-cheap";
                        }
                    }
                }
                
                if (col.startsWith("Diferencia / Oportunidad")) {
                    td.className = "opportunity-cell";
                }
                
                tr.appendChild(td);
            });
            
            mergedResultsBody.appendChild(tr);
        });
        
        // Hacer scroll suave hacia los resultados
        mergedResultsCard.scrollIntoView({ behavior: "smooth" });
    }

    btnClearMerged.addEventListener("click", () => {
        mergedResultsBody.innerHTML = "";
        mergedResultsHeaders.innerHTML = "";
        mergedResultsCard.style.display = "none";
    });

    // Controladores de eventos para carga de archivos
    if (uploadZone && uploadInput) {
        uploadZone.addEventListener("click", () => {
            uploadInput.click();
        });

        uploadInput.addEventListener("change", () => {
            if (uploadInput.files.length > 0) {
                uploadFiles(uploadInput.files);
            }
        });

        uploadZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            uploadZone.classList.add("dragover");
        });

        uploadZone.addEventListener("dragleave", () => {
            uploadZone.classList.remove("dragover");
        });

        uploadZone.addEventListener("drop", (e) => {
            e.preventDefault();
            uploadZone.classList.remove("dragover");
            if (e.dataTransfer.files.length > 0) {
                uploadFiles(e.dataTransfer.files);
            }
        });
    }

    async function uploadFiles(fileList) {
        const formData = new FormData();
        for (let i = 0; i < fileList.length; i++) {
            formData.append("files", fileList[i]);
        }
        
        try {
            const pText = uploadZone.querySelector("p");
            const originalText = pText.textContent;
            pText.textContent = "📤 Subiendo archivos...";
            
            const res = await fetch("/api/extractions/upload", {
                method: "POST",
                body: formData
            });
            
            if (res.ok) {
                pText.textContent = "¡Archivos subidos con éxito! Arrastra más o haz clic para subir.";
                setTimeout(() => {
                    pText.textContent = originalText;
                }, 4000);
                loadExtractionFiles(); // Refrescar lista de archivos
            } else {
                const errData = await res.json();
                alert(`Error al subir archivos: ${errData.detail || "Error interno"}`);
                pText.textContent = "Error al subir. Haz clic o arrastra para intentar de nuevo.";
            }
        } catch (err) {
            console.error("Error subiendo archivos:", err);
            alert("Error de conexión al subir archivos.");
            if (uploadZone) {
                uploadZone.querySelector("p").textContent = "Error de conexión. Haz clic o arrastra para intentar de nuevo.";
            }
        }
    }

    async function sendTextToProcess(text) {
        if (!activeProviderId) {
            alert("Por favor, selecciona un proveedor activo antes de procesar.");
            return;
        }
        
        lastProcessedClipboard = text; // Update the tracking variable to prevent double processing
        
        try {
            const res = await fetch("/api/process-text", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: text })
            });
            if (!res.ok) {
                const errData = await res.json();
                console.error("Error al procesar el texto:", errData.detail);
            }
        } catch (err) {
            console.error("Error en la conexión al enviar el texto:", err);
        }
    }

    // Auto-read clipboard when tab/window recovers focus
    async function checkClipboardOnFocus() {
        if (!monitorToggle.checked || !activeProviderId) {
            return;
        }
        
        // Safeguard for insecure contexts (HTTP) or older browsers where Clipboard API is not available
        if (!navigator.clipboard || !navigator.clipboard.readText) {
            console.log("El portapapeles no está disponible (requiere conexión segura HTTPS o localhost).");
            return;
        }
        
        try {
            // Attempt to read text directly from system clipboard
            const text = await navigator.clipboard.readText();
            if (text && text.trim()) {
                if (text !== lastProcessedClipboard) {
                    sendTextToProcess(text);
                }
            }
        } catch (err) {
            // Silently handle exceptions, e.g. before clipboard permissions are granted
            console.log("No se pudo auto-leer el portapapeles al enfocar (puede requerir permisos en el navegador):", err);
        }
    }

    // Bind focus and visibility events
    window.addEventListener("focus", checkClipboardOnFocus);
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            checkClipboardOnFocus();
        }
    });

    // Intercept manual copy-paste (Ctrl+V) globally on the document
    document.addEventListener("paste", (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        const text = e.clipboardData.getData("text");
        if (text && text.trim()) {
            sendTextToProcess(text);
        }
    });

    // Button to manually trigger paste from clipboard
    btnPasteClipboard.addEventListener("click", async () => {
        if (!navigator.clipboard || !navigator.clipboard.readText) {
            alert("El portapapeles no está disponible en este navegador o requiere una conexión segura (HTTPS).");
            return;
        }
        try {
            const text = await navigator.clipboard.readText();
            if (text && text.trim()) {
                sendTextToProcess(text);
            }
        } catch (err) {
            alert("No se pudo acceder al portapapeles. Asegúrate de dar permisos de portapapeles en el navegador.");
        }
    });

    // Process pasted text in the quick-paste textbox
    pasteInputArea.addEventListener("paste", () => {
        setTimeout(() => {
            const text = pasteInputArea.value;
            if (text && text.trim()) {
                sendTextToProcess(text);
                pasteInputArea.value = "";
            }
        }, 50);
    });

    // ----------------------------------------------------
    // 6. USER MANAGEMENT (Root Only)
    // ----------------------------------------------------
    async function loadRegisteredUsers() {
        try {
            const res = await fetch("/api/users");
            if (!res.ok) return;
            const data = await res.json();
            
            registeredUsersList.innerHTML = "";
            const users = data.users || [];
            
            if (users.length === 0) {
                registeredUsersList.innerHTML = `<p class="empty-text">No hay otros usuarios registrados.</p>`;
                return;
            }
            
            users.forEach(username => {
                const item = document.createElement("div");
                item.className = "provider-item";
                
                const info = document.createElement("div");
                info.className = "provider-info";
                
                const h4 = document.createElement("h4");
                h4.textContent = username;
                
                const pSpan = document.createElement("p");
                pSpan.textContent = "Rol: Usuario Estándar";
                
                info.appendChild(h4);
                info.appendChild(pSpan);
                
                const deleteBtn = document.createElement("button");
                deleteBtn.className = "btn-delete-prov";
                deleteBtn.innerHTML = "🗑️";
                deleteBtn.title = "Eliminar usuario";
                deleteBtn.onclick = () => deleteUser(username);
                
                item.appendChild(info);
                item.appendChild(deleteBtn);
                registeredUsersList.appendChild(item);
            });
        } catch (err) {
            console.error("Error al cargar usuarios:", err);
        }
    }

    async function deleteUser(username) {
        if (!confirm(`¿Seguro que deseas eliminar al usuario '${username}'?`)) return;
        try {
            const res = await fetch(`/api/users/${username}`, { method: "DELETE" });
            if (res.ok) {
                loadRegisteredUsers();
            } else {
                const errData = await res.json();
                alert(`Error al eliminar usuario: ${errData.detail}`);
            }
        } catch (err) {
            console.error("Error al eliminar usuario:", err);
        }
    }

    btnCreateUser.addEventListener("click", async () => {
        const username = newUsernameInput.value.trim();
        const password = newPasswordInput.value;
        
        if (!username || password.length < 6) {
            alert("Por favor, introduce un nombre de usuario y una contraseña de al menos 6 caracteres.");
            return;
        }
        
        try {
            const res = await fetch("/api/users", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });
            
            if (res.ok) {
                newUsernameInput.value = "";
                newPasswordInput.value = "";
                loadRegisteredUsers();
            } else {
                const errData = await res.json();
                alert(`Error al registrar usuario: ${errData.detail}`);
            }
        } catch (err) {
            console.error("Error al crear usuario:", err);
        }
    });

    // ----------------------------------------------------
    // 7. MATRIZ DE STOCK E INVENTARIO ERP
    // ----------------------------------------------------
    const stockUploadZone = document.getElementById("stock-upload-zone");
    const stockUploadInput = document.getElementById("stock-upload-input");
    const stockCategorySelect = document.getElementById("stock-category-select");
    const btnClearStock = document.getElementById("btn-clear-stock");
    const stockCoveragePctBadge = document.getElementById("stock-coverage-pct-badge");
    
    const kpiStockValue = document.getElementById("kpi-stock-value");
    const kpiStockRefs = document.getElementById("kpi-stock-refs");
    const kpiStockQty = document.getElementById("kpi-stock-qty");
    
    const stockMatrixTable = document.getElementById("stock-matrix-table");
    const matrixHeaders = document.getElementById("matrix-headers");
    const matrixBody = document.getElementById("matrix-body");
    
    const stockCellDetailsCard = document.getElementById("stock-cell-details-card");
    const stockDetailsTitle = document.getElementById("stock-details-title");
    const stockDetailsBody = document.getElementById("stock-details-body");
    
    const stockAlertsList = document.getElementById("stock-alerts-list");
    const stockMarketCompCard = document.getElementById("stock-market-comp-card");
    const stockMarketCompTitle = document.getElementById("stock-market-comp-title");
    const stockMarketCompBody = document.getElementById("stock-market-comp-body");

    let currentStockData = null;

    if (stockUploadZone && stockUploadInput) {
        stockUploadZone.addEventListener("click", () => {
            stockUploadInput.click();
        });

        stockUploadInput.addEventListener("change", () => {
            if (stockUploadInput.files.length > 0) {
                uploadStockPdfFile(stockUploadInput.files[0]);
            }
        });

        stockUploadZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            stockUploadZone.classList.add("dragover");
        });

        stockUploadZone.addEventListener("dragleave", () => {
            stockUploadZone.classList.remove("dragover");
        });

        stockUploadZone.addEventListener("drop", (e) => {
            e.preventDefault();
            stockUploadZone.classList.remove("dragover");
            if (e.dataTransfer.files.length > 0) {
                uploadStockPdfFile(e.dataTransfer.files[0]);
            }
        });
    }

    async function uploadStockPdfFile(file) {
        const formData = new FormData();
        formData.append("file", file);
        
        try {
            const pText = stockUploadZone.querySelector("p");
            const originalText = pText.textContent;
            pText.textContent = "📄 Procesando inventario PDF...";
            
            const res = await fetch("/api/stock/upload", {
                method: "POST",
                body: formData
            });
            
            if (res.ok) {
                pText.textContent = "¡Inventario importado con éxito!";
                setTimeout(() => {
                    pText.textContent = originalText;
                }, 4000);
                loadStockMatrix();
            } else {
                const errData = await res.json();
                alert(`Error al procesar PDF de Stock: ${errData.detail || "Formato no válido"}`);
                pText.textContent = "Error al subir. Intenta de nuevo.";
            }
        } catch (err) {
            console.error("Error subiendo PDF:", err);
            alert("Error de conexión al cargar inventario.");
        }
    }

    async function loadStockMatrix(selectedCategory = "") {
        try {
            const url = selectedCategory ? `/api/stock/matrix?category=${encodeURIComponent(selectedCategory)}` : "/api/stock/matrix";
            const res = await fetch(url);
            const data = await res.json();
            currentStockData = data;
            
            // 1. Rellenar selector de categorías
            stockCategorySelect.innerHTML = "";
            if (data.categories && data.categories.length > 0) {
                data.categories.forEach(cat => {
                    const opt = document.createElement("option");
                    opt.value = cat;
                    opt.textContent = cat;
                    if (cat === data.selected_category) {
                        opt.selected = true;
                    }
                    stockCategorySelect.appendChild(opt);
                });
            } else {
                stockCategorySelect.innerHTML = `<option value="">-- Sin datos --</option>`;
            }

            // 2. Pintar KPIs
            kpiStockValue.textContent = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(data.kpis.total_value);
            kpiStockRefs.textContent = data.kpis.total_references;
            kpiStockQty.textContent = data.kpis.total_stock;
            stockCoveragePctBadge.textContent = `Cobertura: ${data.kpis.coverage_pct}%`;

            // 3. Pintar Alertas / Huecos de catálogo
            stockAlertsList.innerHTML = "";
            if (data.alerts && data.alerts.length > 0) {
                data.alerts.forEach(alert => {
                    const box = document.createElement("div");
                    box.className = `alert-box-${alert.type === 'danger' ? 'error' : (alert.type === 'warning' ? 'warning' : 'info')}`;
                    box.style.margin = "0";
                    box.style.fontSize = "12px";
                    box.textContent = alert.message;
                    stockAlertsList.appendChild(box);
                });
            } else {
                stockAlertsList.innerHTML = `<div class="alert-box-success" style="margin:0; font-size:12px;">¡Felicidades! Tienes cobertura del 100% en todos los segmentos.</div>`;
            }

            // Ocultar detalles previos
            stockCellDetailsCard.style.display = "none";
            stockMarketCompCard.style.display = "none";

            const stockBrandList = document.getElementById("stock-brand-breakdown-list");

            // 4. Renderizar Matriz (Tabla)
            if (!data.capacities || data.capacities.length === 0) {
                matrixHeaders.innerHTML = "";
                matrixBody.innerHTML = `<tr><td class="table-empty" style="padding: 40px; text-align: center; color: var(--text-muted);">Sube el PDF valorado de tu almacén para generar la matriz de stock.</td></tr>`;
                if (stockBrandList) {
                    stockBrandList.innerHTML = `<p style="font-size: 11px; color: var(--text-muted);">Sube el stock para ver la distribución.</p>`;
                }
                return;
            }

            // 3.5 Pintar Distribución por Marca
            if (stockBrandList) {
                stockBrandList.innerHTML = "";
                if (data.brands_dist && data.brands_dist.length > 0) {
                    const maxStock = Math.max(...data.brands_dist.map(b => b.stock), 1);
                    data.brands_dist.forEach(b => {
                        const brandRow = document.createElement("div");
                        brandRow.style.display = "flex";
                        brandRow.style.flexDirection = "column";
                        brandRow.style.gap = "4px";
                        
                        const textInfo = document.createElement("div");
                        textInfo.style.display = "flex";
                        textInfo.style.justifyContent = "space-between";
                        textInfo.style.fontSize = "11px";
                        textInfo.innerHTML = `<span style="font-weight: 500;">${b.brand}</span> <span style="color: var(--text-muted);">${b.stock} uds</span>`;
                        
                        const barContainer = document.createElement("div");
                        barContainer.style.width = "100%";
                        barContainer.style.height = "6px";
                        barContainer.style.background = "rgba(255,255,255,0.05)";
                        barContainer.style.borderRadius = "3px";
                        barContainer.style.overflow = "hidden";
                        
                        const pct = (b.stock / maxStock) * 100;
                        const fillBar = document.createElement("div");
                        fillBar.style.width = `${pct}%`;
                        fillBar.style.height = "100%";
                        fillBar.style.background = "var(--primary)";
                        fillBar.style.borderRadius = "3px";
                        
                        barContainer.appendChild(fillBar);
                        brandRow.appendChild(textInfo);
                        brandRow.appendChild(barContainer);
                        stockBrandList.appendChild(brandRow);
                    });
                } else {
                    stockBrandList.innerHTML = `<p style="font-size: 11px; color: var(--text-muted);">Sin datos de marcas.</p>`;
                }
            }

            // Render Headers (Capacidades)
            matrixHeaders.innerHTML = "<th>Marca / Capacidad</th>";
            data.capacities.forEach(cap => {
                const th = document.createElement("th");
                th.textContent = cap;
                matrixHeaders.appendChild(th);
            });

            // Render Rows (Marcas)
            matrixBody.innerHTML = "";
            data.brands.forEach(br => {
                const tr = document.createElement("tr");
                
                // Celda de etiqueta de la fila
                const tdLabel = document.createElement("td");
                tdLabel.className = "matrix-row-label";
                tdLabel.textContent = br;
                tr.appendChild(tdLabel);
                
                // Celdas de cruce (capacidad)
                data.capacities.forEach(cap => {
                    const cellData = data.cells.find(c => c.capacity === cap && c.brand === br);
                    const td = document.createElement("td");
                    td.className = `matrix-cell-interactive`;
                    
                    if (cellData.count === 0) {
                        td.style.background = "rgba(255,255,255,0.01)";
                    }
                    
                    // Crear contenedor para los 3 badges de segmento (E, M, P)
                    const dotsContainer = document.createElement("div");
                    dotsContainer.className = "segment-dots-container";
                    
                    const segmentsKeys = ["E", "M", "P"];
                    const segmentLabels = {
                        "E": "Gama Económica",
                        "M": "Gama Media",
                        "P": "Gama Premium"
                    };
                    
                    segmentsKeys.forEach(key => {
                        const seg = cellData.segments[key];
                        const badge = document.createElement("span");
                        badge.className = `segment-badge segment-badge-${seg.status}`;
                        badge.textContent = key;
                        badge.title = `${segmentLabels[key]}: ${seg.count} referencias (${seg.stock} uds en stock)`;
                        dotsContainer.appendChild(badge);
                    });
                    
                    td.appendChild(dotsContainer);
                    
                    // Texto pequeño con el stock total del cruce
                    const totalText = document.createElement("span");
                    totalText.className = "matrix-stock-count";
                    totalText.style.display = "block";
                    totalText.style.textAlign = "center";
                    totalText.textContent = cellData.count > 0 ? `${cellData.count} ref (${cellData.total_stock} uds)` : "—";
                    td.appendChild(totalText);
                    
                    td.addEventListener("click", () => {
                        // Resaltar celda seleccionada
                        document.querySelectorAll(".matrix-cell-interactive").forEach(c => c.classList.remove("selected-cell"));
                        td.classList.add("selected-cell");
                        showCellDetails(cellData);
                    });
                    
                    tr.appendChild(td);
                });
                
                matrixBody.appendChild(tr);
            });

        } catch (err) {
            console.error("Error cargando matriz:", err);
        }
    }

    function showCellDetails(cellData) {
        stockCellDetailsCard.style.display = "block";
        stockMarketCompCard.style.display = "none";
        
        stockDetailsTitle.textContent = `Referencias de '${cellData.brand}' en ${cellData.capacity}`;
        
        stockDetailsBody.innerHTML = "";
        if (!cellData.products || cellData.products.length === 0) {
            stockDetailsBody.innerHTML = `<tr><td colspan="100%" class="table-empty">No hay productos en este segmento.</td></tr>`;
            return;
        }

        cellData.products.forEach(p => {
            const tr = document.createElement("tr");
            
            const tdSku = document.createElement("td");
            tdSku.style.fontWeight = "bold";
            tdSku.textContent = p.sku;
            
            const tdBrand = document.createElement("td");
            tdBrand.textContent = p.brand;
            
            const tdDesc = document.createElement("td");
            tdDesc.textContent = p.description;
            
            const tdStock = document.createElement("td");
            tdStock.style.textAlign = "center";
            tdStock.textContent = p.stock;
            
            const tdCost = document.createElement("td");
            tdCost.style.textAlign = "center";
            tdCost.textContent = `${p.cost.toFixed(2)} €`;
            
            const tdAction = document.createElement("td");
            tdAction.style.textAlign = "center";
            const btnSearch = document.createElement("button");
            btnSearch.className = "btn btn-secondary btn-sm";
            btnSearch.style.padding = "3px 8px";
            btnSearch.style.fontSize = "11px";
            btnSearch.textContent = "🔍 Mercado";
            btnSearch.title = "Buscar precios de proveedores para este modelo";
            btnSearch.onclick = () => searchMarketPrices(p.sku);
            
            tdAction.appendChild(btnSearch);
            
            tr.appendChild(tdSku);
            tr.appendChild(tdBrand);
            tr.appendChild(tdDesc);
            tr.appendChild(tdStock);
            tr.appendChild(tdCost);
            tr.appendChild(tdAction);
            
            stockDetailsBody.appendChild(tr);
        });
        
        stockCellDetailsCard.scrollIntoView({ behavior: "smooth" });
    }

    async function searchMarketPrices(sku) {
        try {
            const response = await fetch("/api/providers");
            const config = await response.json();
            const providers = config.providers || [];
            
            stockMarketCompCard.style.display = "block";
            stockMarketCompTitle.textContent = `Ofertas del Mercado para el Modelo: ${sku}`;
            stockMarketCompBody.innerHTML = `<tr><td colspan="5" class="table-empty">Buscando ofertas de proveedores en ficheros locales...</td></tr>`;
            
            let allOffers = [];
            
            for (const prov of providers) {
                try {
                    const res = await fetch(`/api/providers/${prov.id}/data`);
                    if (res.ok) {
                        const data = await res.json();
                        const matchedRecords = data.records.filter(r => {
                            const modelVal = r.model || r.modelo || "";
                            return normalizeModelKey(modelVal) === normalizeModelKey(sku);
                        });
                        
                        matchedRecords.forEach(r => {
                            let priceVal = "N/D";
                            for (const [k, v] of Object.entries(r)) {
                                if (k.toLowerCase().includes("price") || k.toLowerCase().includes("precio") || k.toLowerCase() === "pvp") {
                                    if (v && v !== "No disponible") {
                                        priceVal = v;
                                        break;
                                    }
                                }
                            }
                            
                            allOffers.push({
                                product: r.product || r.producto || "Electrodoméstico",
                                model: r.model || r.modelo || sku,
                                provider: prov.name,
                                price: priceVal,
                                attributes: r.attributes || r.atributos || ""
                            });
                        });
                    }
                } catch (e) {
                    console.error(`Error buscando en proveedor ${prov.id}:`, e);
                }
            }
            
            stockMarketCompBody.innerHTML = "";
            if (allOffers.length === 0) {
                stockMarketCompBody.innerHTML = `<tr><td colspan="5" class="table-empty">No se encontraron ofertas de ningún proveedor para este modelo.</td></tr>`;
                return;
            }
            
            allOffers.forEach(o => {
                const tr = document.createElement("tr");
                
                const tdProd = document.createElement("td");
                tdProd.textContent = o.product;
                
                const tdModel = document.createElement("td");
                tdModel.style.fontWeight = "bold";
                tdModel.textContent = o.model;
                
                const tdProv = document.createElement("td");
                tdProv.textContent = o.provider;
                
                const tdPrice = document.createElement("td");
                tdPrice.style.fontWeight = "bold";
                tdPrice.style.color = "var(--success)";
                tdPrice.textContent = typeof o.price === 'number' ? `${o.price.toFixed(2)} €` : o.price;
                
                const tdAttrs = document.createElement("td");
                tdAttrs.textContent = o.attributes;
                
                tr.appendChild(tdProd);
                tr.appendChild(tdModel);
                tr.appendChild(tdProv);
                tr.appendChild(tdPrice);
                tr.appendChild(tdAttrs);
                
                tr.style.cursor = "pointer";
                tr.title = "Copia rápida de este modelo de competidor";
                tr.addEventListener("click", () => {
                    navigator.clipboard.writeText(`${o.product} ${o.model} ${o.price}`);
                    alert(`Modelo copiado al portapapeles: ${o.model}`);
                });

                stockMarketCompBody.appendChild(tr);
            });
            
            stockMarketCompCard.scrollIntoView({ behavior: "smooth" });
        } catch (err) {
            console.error("Error buscando precios de mercado:", err);
        }
    }

    function normalizeModelKey(val) {
        if (!val) return "";
        return String(val).toLowerCase().replace(/[^a-z0-9]/g, "").trim();
    }

    stockCategorySelect.addEventListener("change", () => {
        loadStockMatrix(stockCategorySelect.value);
    });

    btnClearStock.addEventListener("click", async () => {
        if (confirm("¿Estás seguro de que deseas eliminar permanentemente el inventario de stock importado?")) {
            try {
                const res = await fetch("/api/stock/clear", { method: "POST" });
                if (res.ok) {
                    loadStockMatrix();
                }
            } catch (err) {
                console.error("Error limpiando stock:", err);
            }
        }
    });

    // Initialize Page
    initSSEConnection();
    loadStatus();
});

