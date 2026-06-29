// Guarde Clipboard Parser - Core Frontend Logic
document.addEventListener("DOMContentLoaded", () => {
    // State Variables
    let labels = []; // [{name, start, end, text}]
    let currentSelection = null;
    let eventSource = null;
    let activeProviderId = null;
    let savedProviders = [];

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
            "attributes": "Atributos Técnicos",
            "atributos": "Atributos Técnicos"
        };
        return mappings[key] || key;
    }

    async function loadRecentCaptures() {
        if (!activeProviderId) {
            showEmptyRecentTable();
            return;
        }
        
        const provider = savedProviders.find(p => p.id === activeProviderId);
        if (!provider) return;
        
        // Cargar los últimos datos guardados leyendo su archivo local vía una API o similar
        // Para simplificar, la API de backend escribe el archivo pero no hay API dedicada para leerlo completo
        // Crearemos una lectura rápida en backend o simularemos, ¡espera, usemos los datos del log o leamos la extracción!
        // En app.py no hay endpoint directo para leer las capturas de un archivo, vamos a implementar un endpoint rápido en app.py para ver las capturas del proveedor actual
        // Hagamos un edit rápido de app.py para soportar GET /api/providers/{id}/data
        // Pero primero mostremos el esqueleto. Haremos el fetch a /api/providers/${activeProviderId}/data
        try {
            const res = await fetch(`/api/providers/${activeProviderId}/data`);
            if (!res.ok) {
                recentCapturesBody.innerHTML = `<tr><td class="table-empty" colspan="100%">El archivo de extracción aún no existe. Comienza a copiar datos para crearlo.</td></tr>`;
                // Configurar headers vacíos
                recentCapturesHeaders.innerHTML = `<th>Producto / Modelo</th><th>Precio</th><th>Atributos</th><th>Fecha</th>`;
                return;
            }
            const data = await res.json();
            
            if (data.columns && data.columns.length > 0) {
                // Render headers
                recentCapturesHeaders.innerHTML = "";
                data.columns.forEach(col => {
                    const th = document.createElement("th");
                    th.textContent = translateKey(col);
                    recentCapturesHeaders.appendChild(th);
                });
                
                // Render body
                recentCapturesBody.innerHTML = "";
                if (data.records.length === 0) {
                    recentCapturesBody.innerHTML = `<tr><td class="table-empty" colspan="100%">No hay registros en este archivo.</td></tr>`;
                } else {
                    // Mostrar los últimos 10 de forma invertida (más reciente primero)
                    const displayData = data.records.slice(-10).reverse();
                    displayData.forEach(row => {
                        const tr = document.createElement("tr");
                        data.columns.forEach(col => {
                            const td = document.createElement("td");
                            td.textContent = row[col] !== null ? row[col] : "";
                            tr.appendChild(td);
                        });
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
        recentCapturesHeaders.innerHTML = `<th>Producto / Modelo</th><th>Precio</th><th>Atributos</th><th>Fecha</th>`;
        recentCapturesBody.innerHTML = `<tr><td class="table-empty" colspan="100%">Selecciona un proveedor activo para visualizar sus capturas locales.</td></tr>`;
    }

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
            if (!currentSelection) {
                alert("Primero selecciona/sombrea un fragmento de texto en la caja.");
                return;
            }
            
            const tagName = btn.dataset.tag;
            
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
                
                label.appendChild(checkbox);
                label.appendChild(span);
                label.appendChild(info);
                filesChecklist.appendChild(label);
            });
        } catch (err) {
            console.error("Error al cargar archivos:", err);
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
        
        // Render headers
        mergedResultsHeaders.innerHTML = "";
        result.columns.forEach(col => {
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
            
            // Determinar cuál es el precio mínimo en esta fila
            let minPrice = Infinity;
            let priceColsInRow = [];
            
            result.columns.forEach(col => {
                if (col.startsWith("Precio ") && col.endsWith(" (€)")) {
                    const val = parseFloat(row[col]);
                    if (!isNaN(val) && val > 0) {
                        priceColsInRow.push({ col: col, val: val });
                        if (val < minPrice) {
                            minPrice = val;
                        }
                    }
                }
            });
            
            result.columns.forEach(col => {
                const td = document.createElement("td");
                const val = row[col];
                td.textContent = val !== null ? val : "";
                
                // Si es el precio más barato de esta fila, destacarlo
                if (col.startsWith("Precio ") && col.endsWith(" (€)")) {
                    const priceVal = parseFloat(val);
                    if (!isNaN(priceVal) && priceVal === minPrice && priceColsInRow.length > 1) {
                        td.className = "highlight-cheap";
                    }
                }
                
                if (col === "Diferencia / Oportunidad") {
                    td.className = "opportunity-cell";
                }
                
                tr.appendChild(td);
            });
            
            mergedResultsBody.appendChild(tr);
        });
        
        // Hacer scroll suave hacia los resultados
        mergedResultsCard.scrollIntoView({ behavior: "smooth" });
    }

    // Initialize Page
    initSSEConnection();
    loadStatus();
});
