// Guarde Clipboard Parser - Core Frontend Logic
document.addEventListener("DOMContentLoaded", () => {
    // State Variables
    let labels = []; // [{name, start, end, text}]
    let currentSelection = null;
    let eventSource = null;
    let activeProviderId = null;
    let lastProcessedClipboard = "";
    let suppressClipboardAutoCheck = false;
    let recentAiSentTexts = new Map();
    let deletedItemsSet = new Set();
    let currentRecentRecords = [];
    let currentStockData = null;
    let activeBatchPages = 0;

    function isItemDeletedOrSuppressed(text) {
        if (!text) return false;
        const lower = text.trim().toLowerCase();
        if (deletedItemsSet.has(lower)) return true;
        for (const item of deletedItemsSet) {
            if (item.length >= 4 && lower.includes(item)) {
                return true;
            }
        }
        return false;
    }

    async function syncClipboardTracking() {
        if (navigator.clipboard && navigator.clipboard.readText) {
            try {
                const currentText = await navigator.clipboard.readText();
                if (currentText) {
                    const clean = currentText.trim();
                    lastProcessedClipboard = clean;
                    deletedItemsSet.add(clean.toLowerCase());
                }
            } catch (e) {}
        }
    }

    function showConfirmDialog(title, message, isDanger = true) {
        return new Promise((resolve) => {
            suppressClipboardAutoCheck = true;
            const modal = document.getElementById("modal-confirm");
            const titleEl = document.getElementById("modal-confirm-title");
            const msgEl = document.getElementById("modal-confirm-message");
            const btnOk = document.getElementById("modal-confirm-ok");
            const btnCancel = document.getElementById("modal-confirm-cancel");
            const btnClose = document.getElementById("modal-confirm-close");

            if (!modal) {
                const res = confirm(message);
                syncClipboardTracking();
                setTimeout(() => { suppressClipboardAutoCheck = false; }, 1500);
                return resolve(res);
            }

            titleEl.textContent = title || "Confirmar acción";
            msgEl.textContent = message || "¿Estás seguro de realizar esta acción?";
            btnOk.className = isDanger ? "btn btn-danger btn-sm" : "btn btn-primary btn-sm";
            btnOk.textContent = isDanger ? "Sí, eliminar" : "Aceptar";

            modal.style.display = "flex";

            async function finish(result) {
                modal.style.display = "none";
                btnOk.onclick = null;
                btnCancel.onclick = null;
                btnClose.onclick = null;
                await syncClipboardTracking();
                setTimeout(() => {
                    suppressClipboardAutoCheck = false;
                }, 3000);
                resolve(result);
            }

            btnOk.onclick = async () => {
                await syncClipboardTracking();
                finish(true);
            };
            btnCancel.onclick = () => finish(false);
            btnClose.onclick = () => finish(false);
        });
    }

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
    const btnExtractTextAi = document.getElementById("btn-extract-text-ai");
    const btnModeGemini = document.getElementById("btn-mode-gemini");
    const btnModeRegex = document.getElementById("btn-mode-regex");
    const clipboardModeBadge = document.getElementById("clipboard-mode-badge");
    const clipboardModeDesc = document.getElementById("clipboard-mode-desc");
    const pasteInputArea = document.getElementById("paste-input-area");
    const imageOcrDropzone = document.getElementById("image-ocr-dropzone");
    const imageFileInput = document.getElementById("image-file-input");
    const batchOcrCard = document.getElementById("batch-ocr-card");
    const batchCounterBadge = document.getElementById("batch-counter-badge");
    const btnAddBatchImages = document.getElementById("btn-add-batch-images");
    const btnClearBatchImages = document.getElementById("btn-clear-batch-images");
    const btnFinishBatch = document.getElementById("btn-finish-batch");

    // Gemini AI / Engine Elements
    const imageEngineSelect = document.getElementById("image-engine-select");
    const geminiKeyStatus = document.getElementById("gemini-key-status");
    const btnConfigGemini = document.getElementById("btn-config-gemini");
    const geminiConfigCard = document.getElementById("gemini-config-card");
    const btnCloseGeminiConfig = document.getElementById("btn-close-gemini-config");
    const geminiApiKeyInput = document.getElementById("gemini-api-key-input");
    const btnToggleShowKey = document.getElementById("btn-toggle-show-key");
    const btnSaveGeminiKey = document.getElementById("btn-save-gemini-key");
    const geminiConfigMsg = document.getElementById("gemini-config-msg");
    const geminiFallbackCheckbox = document.getElementById("gemini-fallback-checkbox");
    // Tab 2 Elements
    const savedProvidersList = document.getElementById("saved-providers-list");
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
    const btnTestCustomRegex = document.getElementById("btn-test-custom-regex");
    const regexMatchStatus = document.getElementById("regex-match-status");
    const extractedFieldsJson = document.getElementById("extracted-fields-json");
    const clearSelectionsBtn = document.getElementById("clear-selections");
    const btnAutoSuggestLabels = document.getElementById("btn-auto-suggest-labels");
    const multiCardPreviewSection = document.getElementById("multi-card-preview-section");
    const tagButtons = document.querySelectorAll(".tag-btn[data-tag]");

    function getGeneratedRegex() {
        const el = generatedRegexString || document.getElementById("generated-regex-string");
        if (!el) return "";
        return (el.value !== undefined ? el.value : el.textContent || "").trim();
    }

    function setGeneratedRegex(val) {
        const el = generatedRegexString || document.getElementById("generated-regex-string");
        if (!el) return;
        if (el.value !== undefined) {
            el.value = val;
        }
        el.textContent = val;
    }
    
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
            } else if (tab.dataset.tab === "tab-shortages") {
                initAuditTab();
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

    // Image OCR Processing Function & Event Listeners
    async function uploadAndProcessImages(filesInput) {
        if (!filesInput) return;
        let filesArr = [];
        if (filesInput instanceof FileList || Array.isArray(filesInput)) {
            filesArr = Array.from(filesInput);
        } else if (filesInput instanceof File) {
            filesArr = [filesInput];
        }

        if (filesArr.length === 0) return;

        const formData = new FormData();
        filesArr.forEach(file => {
            formData.append("files", file);
        });

        const engine = imageEngineSelect ? imageEngineSelect.value : "gemini";
        formData.append("engine", engine);

        const engineLabel = engine === "gemini" ? "la IA de Gemini Vision" : "el OCR local";
        const labelMsg = filesArr.length === 1 
            ? `'${filesArr[0].name || 'captura.png'}'`
            : `${filesArr.length} imágenes (multi-página)`;

        appendLog({
            timestamp: new Date().toLocaleTimeString(),
            type: "info",
            message: `Enviando ${labelMsg} a ${engineLabel}...`
        });

        try {
            const response = await fetch("/api/parse-image", {
                method: "POST",
                body: formData
            });
            let data;
            try {
                data = await response.json();
            } catch (_) {
                const txt = await response.text();
                data = { status: "error", message: `Error del servidor (${response.status}): ${txt}` };
            }
            if (response.ok && (data.status === "success" || data.status === "warning")) {
                const addedPages = data.images_processed || 0;
                if (addedPages > 0) {
                    activeBatchPages += addedPages;
                }

                const msgType = data.status === "success" ? "success" : "warning";
                appendLog({
                    timestamp: new Date().toLocaleTimeString(),
                    type: msgType,
                    message: data.message || `Procesada(s) ${addedPages} página(s) (${engine === "gemini" ? "IA Gemini" : "OCR"}).`
                });

                if (data.status === "success" && batchOcrCard && batchCounterBadge) {
                    batchOcrCard.style.display = "block";
                    batchCounterBadge.textContent = `${activeBatchPages} página(s) en lote activo`;
                }

                // Si el backend asignó o confirmó un proveedor, sincronizarlo y activarlo de inmediato
                const targetId = data.active_provider_id || data.target_provider_id || (data.target_provider ? data.target_provider.id : null);
                if (targetId && (!activeProviderId || activeProviderId !== targetId)) {
                    await loadProviders(targetId);
                    await activateProvider(targetId);
                } else {
                    await loadRecentCaptures();
                }
            } else {
                appendLog({
                    timestamp: new Date().toLocaleTimeString(),
                    type: "error",
                    message: data.message || "Error procesando imágenes."
                });
            }
        } catch (err) {
            appendLog({
                timestamp: new Date().toLocaleTimeString(),
                type: "error",
                message: "Error de red al procesar las imágenes: " + err.message
            });
        }
    }

    function finishOcrBatch() {
        if (activeBatchPages > 0) {
            appendLog({
                timestamp: new Date().toLocaleTimeString(),
                type: "success",
                message: `🏁 Lote multi-página finalizado. Se completó el procesado de ${activeBatchPages} página(s) de imágenes.`
            });
        } else {
            appendLog({
                timestamp: new Date().toLocaleTimeString(),
                type: "info",
                message: "🏁 Lote finalizado."
            });
        }

        activeBatchPages = 0;
        if (batchOcrCard) {
            batchOcrCard.style.display = "none";
        }
        loadRecentCaptures();
    }

    if (btnAddBatchImages && imageFileInput) {
        btnAddBatchImages.addEventListener("click", (e) => {
            e.stopPropagation();
            imageFileInput.click();
        });
    }

    if (btnClearBatchImages) {
        btnClearBatchImages.addEventListener("click", async (e) => {
            e.stopPropagation();
            if (!activeProviderId) return;
            const ok = await showConfirmDialog(
                "Vaciar capturas del lote",
                "¿Estás seguro de que deseas vaciar y eliminar todas las capturas registradas de este lote/proveedor?",
                true
            );
            if (ok) {
                suppressClipboardAutoCheck = true;
                await syncClipboardTracking();
                try {
                    const res = await fetch(`/api/providers/${activeProviderId}/clear`, {
                        method: "POST"
                    });
                    if (res.ok) {
                        activeBatchPages = 0;
                        if (batchOcrCard) batchOcrCard.style.display = "none";
                        appendLog({
                            timestamp: new Date().toLocaleTimeString(),
                            type: "info",
                            message: "🗑️ Listado de capturas vaciado correctamente."
                        });
                        await loadRecentCaptures();
                    } else {
                        alert("Error al intentar limpiar las capturas del lote.");
                    }
                } catch (err) {
                    console.error("Error al vaciar lote:", err);
                } finally {
                    await syncClipboardTracking();
                    setTimeout(() => { suppressClipboardAutoCheck = false; }, 2000);
                }
            }
        });
    }

    if (btnFinishBatch) {
        btnFinishBatch.addEventListener("click", (e) => {
            e.stopPropagation();
            finishOcrBatch();
        });
    }

    if (imageOcrDropzone && imageFileInput) {
        imageOcrDropzone.addEventListener("click", () => imageFileInput.click());
        
        imageFileInput.addEventListener("change", (e) => {
            if (e.target.files && e.target.files.length > 0) {
                uploadAndProcessImages(e.target.files);
                imageFileInput.value = "";
            }
        });

        imageOcrDropzone.addEventListener("dragover", (e) => {
            e.preventDefault();
            imageOcrDropzone.classList.add("dragover");
        });

        imageOcrDropzone.addEventListener("dragleave", () => {
            imageOcrDropzone.classList.remove("dragover");
        });

        imageOcrDropzone.addEventListener("drop", (e) => {
            e.preventDefault();
            imageOcrDropzone.classList.remove("dragover");
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                uploadAndProcessImages(e.dataTransfer.files);
            }
        });
    }

    // Escucha global de pegado (Ctrl+V) para capturas de pantalla de la competencia
    window.addEventListener("paste", (e) => {
        const items = (e.clipboardData || (e.originalEvent && e.originalEvent.clipboardData))?.items;
        if (!items) return;

        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf("image") !== -1) {
                const blob = items[i].getAsFile();
                if (blob) {
                    e.preventDefault();
                    uploadAndProcessImages(blob);
                    break;
                }
            }
        }
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
    let isUpdatingSelect = false;

    async function loadStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();
            
            monitorToggle.checked = data.is_monitoring;
            activeProviderId = data.active_provider ? data.active_provider.id : null;
            
            updateActiveBadge(data.active_provider);
            await loadProviders(activeProviderId);
            
            if (activeProviderId) {
                isUpdatingSelect = true;
                providerSelect.value = activeProviderId;
                isUpdatingSelect = false;
                await loadRecentCaptures();
            } else if (savedProviders && savedProviders.length > 0) {
                // Si el backend no tiene proveedor activo, activar automáticamente el primero
                await activateProvider(savedProviders[0].id);
            } else {
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

    async function activateProvider(id) {
        try {
            const res = await fetch("/api/providers/select", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ provider_id: id || null })
            });
            const data = await res.json();
            activeProviderId = data.active_provider ? data.active_provider.id : null;
            updateActiveBadge(data.active_provider);

            // Sincronizar el selector sin disparar el evento change
            isUpdatingSelect = true;
            providerSelect.value = activeProviderId || "";
            isUpdatingSelect = false;

            // Sincronizar elemento activo en la lista lateral
            document.querySelectorAll(".provider-item").forEach(item => {
                item.classList.toggle("active", item.dataset.id === activeProviderId);
            });

            lastProcessedClipboard = ""; // Reset duplicate detection on provider change
            await loadRecentCaptures();
        } catch (err) {
            console.error("Error al activar proveedor:", err);
        }
    }

    providerSelect.addEventListener("change", async () => {
        if (isUpdatingSelect) return;
        const val = providerSelect.value ? providerSelect.value.trim() : null;
        await activateProvider(val);
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
            "Tipo de Aparato": "Tipo de Aparato",
            "Marca": "Marca",
            "Modelo": "Modelo / SKU",
            "Descripción": "Descripción / Producto",
            "Atributos": "Atributos Técnicos",
            "Sin IVA (€)": "Sin IVA (€)",
            "Con IVA (€)": "Con IVA (€)",
            "PVP (€)": "PVP (€)",
            "Fecha": "Fecha / Hora",
            "category": "Tipo de Aparato",
            "categoria": "Tipo de Aparato",
            "tipo_aparato": "Tipo de Aparato",
            "tipo": "Tipo de Aparato",
            "brand": "Marca",
            "marca": "Marca",
            "product": "Descripción",
            "producto": "Descripción",
            "descripcion": "Descripción",
            "model": "Modelo / SKU",
            "modelo": "Modelo / SKU",
            "price": "Sin IVA (€)",
            "precio": "Sin IVA (€)",
            "price_no_vat": "Sin IVA (€)",
            "precio_sin_iva": "Sin IVA (€)",
            "sin_iva": "Sin IVA (€)",
            "no_vat": "Sin IVA (€)",
            "price_vat": "Con IVA (€)",
            "precio_con_iva": "Con IVA (€)",
            "con_iva": "Con IVA (€)",
            "vat": "Con IVA (€)",
            "pvp": "PVP (€)",
            "precio_pvp": "PVP (€)",
            "attributes": "Atributos Técnicos",
            "atributos": "Atributos Técnicos",
            "timestamp": "Fecha / Hora"
        };
        return mappings[key] || key;
    }

    async function loadRecentCaptures() {
        if (!activeProviderId) {
            showEmptyRecentTable();
            return;
        }
        
        btnDownloadRaw.href = `/api/extractions/download/${activeProviderId}`;
        btnDownloadRaw.style.display = "inline-block";
        btnClearCaptures.style.display = "inline-block";
        
        let provider = savedProviders.find(p => p.id === activeProviderId);
        if (!provider && activeProviderId === "default") {
            provider = { id: "default", name: "General", file_format: "csv", fields: [] };
        }
        if (!provider) return;
        
        const ext = provider.file_format || "csv";
        btnDownloadRaw.setAttribute("download", `${provider.id}.${ext}`);
        
        try {
            const res = await fetch(`/api/providers/${activeProviderId}/data`);
            if (!res.ok) {
                recentCapturesBody.innerHTML = `<tr><td class="table-empty" colspan="100%">El archivo de extracción aún no existe. Comienza a copiar datos para crearlo.</td></tr>`;
                recentCapturesHeaders.innerHTML = `<th>Tipo de Aparato</th><th>Marca</th><th>Modelo</th><th>Descripción</th><th>Atributos</th><th>Sin IVA (€)</th><th>Con IVA (€)</th><th>PVP (€)</th><th>Fecha</th><th>Acciones</th>`;
                btnClearCaptures.style.display = "none";
                btnDownloadRaw.style.display = "none";
                return;
            }
            const data = await res.json();
            currentRecentRecords = data.records || [];
            
            if (data.columns && data.columns.length > 0) {
                // Render headers
                recentCapturesHeaders.innerHTML = "";
                data.columns.forEach(col => {
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
                            const td = document.createElement("td");
                            td.textContent = row[col] !== null && row[col] !== undefined ? row[col] : "";
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
                            suppressClipboardAutoCheck = true;
                            await syncClipboardTracking();
                            const ok = await showConfirmDialog(
                                "Eliminar captura",
                                "¿Estás seguro de que deseas eliminar esta captura específica de la lista?",
                                true
                            );
                            if (ok) {
                                await deleteCaptureRow(row._index, row);
                            } else {
                                setTimeout(() => { suppressClipboardAutoCheck = false; }, 2000);
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

    async function deleteCaptureRow(index, rowData = null) {
        suppressClipboardAutoCheck = true;
        if (rowData) {
            Object.values(rowData).forEach(v => {
                if (v && typeof v === 'string' && v.trim().length >= 3) {
                    deletedItemsSet.add(v.trim().toLowerCase());
                }
            });
        }
        await syncClipboardTracking();
        try {
            const res = await fetch(`/api/providers/${activeProviderId}/delete-row`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ index: index })
            });
            if (res.ok) {
                await loadRecentCaptures();
            } else {
                alert("Error al intentar eliminar la captura.");
            }
        } catch (err) {
            console.error("Error eliminando captura:", err);
        } finally {
            await syncClipboardTracking();
            setTimeout(() => { suppressClipboardAutoCheck = false; }, 4000);
        }
    }

    btnClearCaptures.addEventListener("click", async () => {
        if (!activeProviderId) return;
        suppressClipboardAutoCheck = true;
        await syncClipboardTracking();
        const ok = await showConfirmDialog(
            "Vaciar capturas del proveedor",
            "¿Estás seguro de que deseas vaciar y eliminar todas las capturas de este proveedor? Esta acción no se puede deshacer.",
            true
        );
        if (ok) {
            suppressClipboardAutoCheck = true;
            if (currentRecentRecords && currentRecentRecords.length) {
                currentRecentRecords.forEach(row => {
                    Object.values(row).forEach(v => {
                        if (v && typeof v === 'string' && v.trim().length >= 3) {
                            deletedItemsSet.add(v.trim().toLowerCase());
                        }
                    });
                });
            }
            await syncClipboardTracking();
            try {
                const res = await fetch(`/api/providers/${activeProviderId}/clear`, {
                    method: "POST"
                });
                if (res.ok) {
                    await loadRecentCaptures();
                } else {
                    alert("Error al intentar limpiar las capturas.");
                }
            } catch (err) {
                console.error("Error limpiando capturas:", err);
            } finally {
                await syncClipboardTracking();
                setTimeout(() => { suppressClipboardAutoCheck = false; }, 4000);
            }
        } else {
            setTimeout(() => { suppressClipboardAutoCheck = false; }, 2000);
        }
    });

    // ----------------------------------------------------
    // 4. NO-CODE REGEX TRAINING & ASSISTANT
    // ----------------------------------------------------
    async function loadProviders(selectId = null) {
        try {
            const res = await fetch("/api/providers");
            const data = await res.json();
            savedProviders = data.providers || [];
            
            if (selectId) {
                activeProviderId = selectId;
            } else if (data.active_provider_id && !activeProviderId) {
                activeProviderId = data.active_provider_id;
            }
            
            // Popular sidebar de plantillas guardadas
            const listEl = savedProvidersList || document.getElementById("saved-providers-list");
            if (listEl) {
                listEl.innerHTML = "";
                if (savedProviders.length === 0) {
                    listEl.innerHTML = `<p class="empty-text" style="color: var(--text-muted); font-size: 13px; padding: 10px;">No hay plantillas guardadas.</p>`;
                } else {
                    savedProviders.forEach(p => {
                        const item = document.createElement("div");
                        item.className = `provider-item ${p.id === activeProviderId ? 'active' : ''}`;
                        item.dataset.id = p.id;
                        item.onclick = () => {
                            loadProviderIntoTrainer(p);
                            activateProvider(p.id);
                        };
                        
                        const info = document.createElement("div");
                        info.className = "provider-info";
                        
                        const h4 = document.createElement("h4");
                        h4.textContent = p.name;
                        
                        const pSpan = document.createElement("p");
                        const fieldsList = (p.fields && p.fields.length > 0) ? p.fields.join(", ") : "Sin campos";
                        const formatStr = (p.file_format || "xlsx").toUpperCase();
                        pSpan.textContent = `Campos: ${fieldsList} (${formatStr})`;
                        
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
                        listEl.appendChild(item);
                    });
                }
            }
            
            // Popular selector protegido contra eventos change no deseados
            const targetId = selectId || activeProviderId || "";
            isUpdatingSelect = true;
            providerSelect.innerHTML = `<option value="">-- Seleccionar Proveedor --</option>`;
            savedProviders.forEach(p => {
                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = p.name;
                if (p.id === targetId) opt.selected = true;
                providerSelect.appendChild(opt);
            });
            // Opción General para capturas sin plantilla previa
            const optDefault = document.createElement("option");
            optDefault.value = "default";
            optDefault.textContent = "📁 General (Capturas Rápidas / IA)";
            if (targetId === "default") optDefault.selected = true;
            providerSelect.appendChild(optDefault);

            if (targetId && (savedProviders.some(p => p.id === targetId) || targetId === "default")) {
                providerSelect.value = targetId;
            }
            isUpdatingSelect = false;
        } catch (err) {
            console.error("Error al cargar proveedores:", err);
        }
    }

    function loadProviderIntoTrainer(p) {
        if (!p) return;
        provNameInput.value = p.name || "";
        provIdInput.value = p.id || "";
        provIdInput.dataset.autogen = "false";
        provFormatSelect.value = p.file_format || "xlsx";
        const sample = p.sample_text || "";
        rawTrainText.value = sample;
        
        // Mapear etiquetas asegurando índices enteros y texto asignado
        labels = (Array.isArray(p.labels) ? p.labels : []).map(l => {
            const s = parseInt(l.start) || 0;
            const e = parseInt(l.end) || 0;
            return {
                name: l.name,
                start: s,
                end: e,
                text: l.text || (sample ? sample.substring(s, e) : "") || l.name
            };
        });
        
        // Cargar regex existente si existe
        if (p.regex && p.regex !== "^...$") {
            setGeneratedRegex(p.regex);
            regexResultsCard.style.display = "block";
            regexMatchStatus.className = "regex-match-status status-box-success";
            regexMatchStatus.textContent = "✓ Expresión regular cargada desde la plantilla.";
            extractedFieldsJson.textContent = "{}";
        } else {
            setGeneratedRegex("^...$");
            regexResultsCard.style.display = "none";
        }
        
        // Disparar renderizado del workspace
        if (sample) {
            labelingWorkspace.style.display = "block";
            activeTagsSection.style.display = "block";
            renderInteractiveText();
        } else {
            labelingWorkspace.style.display = "none";
            activeTagsSection.style.display = "none";
            renderTagsBadges();
        }
        btnSaveProvider.disabled = false;
        
        // Si no tiene regex previa y hay etiquetas y muestra, generar automáticamente
        if ((!p.regex || p.regex === "^...$" || p.regex === ".*") && labels.length > 0 && sample) {
            generateAndTestRegex();
        } else if (p.regex && p.regex !== "^...$" && p.regex !== ".*" && sample) {
            // Probar la regex existente contra la muestra para actualizar vista previa
            testCurrentRegex(false);
        }
    }

    async function deleteProvider(id) {
        if (!confirm(`¿Seguro que deseas eliminar la plantilla del proveedor '${id}'?`)) return;
        try {
            await fetch(`/api/providers/${id}`, { method: "DELETE" });
            if (activeProviderId === id) activeProviderId = null;
            await loadProviders();
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
            // Filtrar etiquetas que queden fuera de rango si se acortó el texto
            labels = labels.filter(l => l.start < text.length && l.end <= text.length);
            renderInteractiveText();
        } else {
            labelingWorkspace.style.display = "none";
            activeTagsSection.style.display = "none";
            regexResultsCard.style.display = "none";
            labels = [];
        }
        btnSaveProvider.disabled = false;
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
            btnSaveProvider.disabled = false;
        });
    });

    clearSelectionsBtn.addEventListener("click", () => {
        labels = [];
        currentSelection = null;
        renderInteractiveText();
        regexResultsCard.style.display = "none";
        btnSaveProvider.disabled = false;
    });

    function renderInteractiveText() {
        const rawText = rawTrainText.value || "";
        if (!rawText) {
            interactiveTextBox.innerHTML = "";
            renderTagsBadges();
            return;
        }
        
        const sorted = [...labels].sort((a, b) => a.start - b.start);
        let html = "";
        let lastIdx = 0;
        
        sorted.forEach(l => {
            const start = Math.max(0, Math.min(l.start, rawText.length));
            const end = Math.max(start, Math.min(l.end, rawText.length));
            if (start > lastIdx) {
                html += escapeHtml(rawText.substring(lastIdx, start));
            }
            if (end > start) {
                html += `<span class="tagged-span tagged-${l.name}">${escapeHtml(rawText.substring(start, end))}</span>`;
                lastIdx = end;
            }
        });
        if (lastIdx < rawText.length) {
            html += escapeHtml(rawText.substring(lastIdx));
        }
        
        interactiveTextBox.innerHTML = html;
        renderTagsBadges();
    }

    function renderTagsBadges() {
        tagsBadgeContainer.innerHTML = "";
        if (!labels || labels.length === 0) {
            tagsBadgeContainer.innerHTML = `<span style="font-size:12px; color:var(--text-muted);">Sin etiquetas asignadas</span>`;
            return;
        }
        
        const rawText = rawTrainText.value || "";
        labels.forEach((l, idx) => {
            const valText = l.text || (rawText ? rawText.substring(l.start, l.end) : "") || l.name;
            const badge = document.createElement("span");
            badge.className = `tag-badge badge-${l.name}`;
            badge.innerHTML = `${translateKey(l.name)}: "<strong>${escapeHtml(valText)}</strong>"`;
            
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
        if (text === null || text === undefined) return "";
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    if (btnAutoSuggestLabels) {
        btnAutoSuggestLabels.addEventListener("click", async () => {
            const rawText = rawTrainText.value;
            if (!rawText || !rawText.trim()) {
                alert("Pega primero un texto de muestra en la caja de 'Texto Bruto de Muestra'.");
                return;
            }
            const origHtml = btnAutoSuggestLabels.innerHTML;
            btnAutoSuggestLabels.disabled = true;
            btnAutoSuggestLabels.innerHTML = "⏳ Analizando con IA...";

            try {
                const res = await fetch("/api/regex/suggest-labels", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ raw_text: rawText })
                });
                const data = await res.json();
                if (data.status === "success" && data.labels && data.labels.length > 0) {
                    labels = data.labels;
                    labelingWorkspace.style.display = "block";
                    activeTagsSection.style.display = "block";
                    renderInteractiveText();
                    generateAndTestRegex();
                } else {
                    alert("No se pudieron detectar etiquetas automáticas en este texto. Puedes marcarlas manualmente.");
                }
            } catch (err) {
                console.error("Error al auto-sugerir etiquetas:", err);
                alert("Ocurrió un error al contactar al backend para sugerir etiquetas.");
            } finally {
                btnAutoSuggestLabels.disabled = false;
                btnAutoSuggestLabels.innerHTML = origHtml;
            }
        });
    }

    if (btnTestCustomRegex) {
        btnTestCustomRegex.addEventListener("click", () => testCurrentRegex(true));
    }

    if (generatedRegexString) {
        generatedRegexString.addEventListener("input", () => {
            btnSaveProvider.disabled = false;
        });
    }

    async function testCurrentRegex(showAlerts = true) {
        const pattern = getGeneratedRegex();
        const sample = (rawTrainText.value || "").trim();
        if (!pattern || pattern === "^...$") {
            if (showAlerts) alert("No hay ningún regex para probar. Genera uno primero o escríbelo en el campo.");
            return;
        }
        if (!sample) {
            if (showAlerts) alert("Introduce primero un texto de muestra en 'Texto Bruto de Muestra'.");
            return;
        }
        
        try {
            const res = await fetch("/api/regex/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ regex: pattern, text: sample })
            });
            const data = await res.json();
            
            regexResultsCard.style.display = "block";
            if (data.status === "success" && data.matches && data.matches.length > 0) {
                regexMatchStatus.className = "regex-match-status status-box-success";
                regexMatchStatus.textContent = `✓ ${data.message || `El regex coincide con ${data.matches.length} elemento(s).`}`;
                extractedFieldsJson.textContent = JSON.stringify(data.extracted || {}, null, 2);
                
                // Renderizar preview multi-ficha
                let multiHtml = `
                    <div style="background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 8px; padding: 14px; margin-top: 10px;">
                        <h4 style="margin: 0 0 10px 0; font-size: 14px; color: #818cf8; display: flex; align-items: center; justify-content: space-between;">
                            <span>🎯 Coincidencias del Regex:</span>
                            <span style="background: #6366f1; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;">${data.matches.length} Encontrados</span>
                        </h4>
                        <div style="display: flex; flex-direction: column; gap: 8px; max-height: 280px; overflow-y: auto;">
                `;
                data.matches.forEach((item, idx) => {
                    multiHtml += `
                        <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 10px;">
                            <div style="font-weight: 600; font-size: 12px; color: #94a3b8; margin-bottom: 6px;">Coincidencia #${idx + 1}:</div>
                            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                    `;
                    for (const [k, v] of Object.entries(item)) {
                        if (v) multiHtml += `<span class="tag-badge badge-${k}" style="font-size: 11px; padding: 3px 8px;">${translateKey(k)}: <strong>${escapeHtml(String(v))}</strong></span>`;
                    }
                    multiHtml += `</div></div>`;
                });
                multiHtml += `</div></div>`;
                multiCardPreviewSection.innerHTML = multiHtml;
                multiCardPreviewSection.style.display = "block";
            } else if (data.status === "warning") {
                regexMatchStatus.className = "regex-match-status status-box-warning";
                regexMatchStatus.textContent = `⚠ ${data.message || "El regex no coincide con el texto de muestra actual."}`;
                if (showAlerts) {
                    extractedFieldsJson.textContent = "{}";
                    multiCardPreviewSection.style.display = "none";
                }
            } else {
                regexMatchStatus.className = "regex-match-status status-box-error";
                regexMatchStatus.textContent = `✗ ${data.message || "Error al validar la expresión regular"}`;
                if (showAlerts) {
                    extractedFieldsJson.textContent = "{}";
                    multiCardPreviewSection.style.display = "none";
                }
            }
        } catch (e) {
            console.error("Error al probar regex:", e);
            if (showAlerts) {
                regexMatchStatus.className = "regex-match-status status-box-error";
                regexMatchStatus.textContent = `✗ Error de conexión al validar regex: ${e.message}`;
            }
        }
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
            setGeneratedRegex(data.regex || "");
            
            if (data.status === "success" || data.status === "warning") {
                if (data.status === "success") {
                    regexMatchStatus.className = "regex-match-status status-box-success";
                    regexMatchStatus.textContent = "✓ ¡Éxito! La expresión regular coincide perfectamente con el texto de muestra.";
                } else {
                    regexMatchStatus.className = "regex-match-status status-box-warning";
                    regexMatchStatus.textContent = `⚠ ${data.message} (Puedes guardar la plantilla seleccionando únicamente los colores/campos que te interesen).`;
                }
                extractedFieldsJson.textContent = JSON.stringify(data.extracted || {}, null, 2);
                btnSaveProvider.disabled = false;

                // Renderizar vista previa multi-ficha en tiempo real
                if (data.all_matches && data.all_matches.length > 0) {
                    let multiHtml = `
                        <div style="background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 8px; padding: 14px; margin-top: 10px;">
                            <h4 style="margin: 0 0 10px 0; font-size: 14px; color: #818cf8; display: flex; align-items: center; justify-content: space-between;">
                                <span>🎯 Vista Previa Multi-Ficha en Tiempo Real:</span>
                                <span style="background: #6366f1; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;">${data.total_matched_cards} Fichas Coincidentes</span>
                            </h4>
                            <div style="display: flex; flex-direction: column; gap: 8px; max-height: 280px; overflow-y: auto; padding-right: 4px;">
                    `;

                    data.all_matches.forEach((item, idx) => {
                        multiHtml += `
                            <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 10px;">
                                <div style="font-weight: 600; font-size: 12px; color: #94a3b8; margin-bottom: 6px;">Ficha #${idx + 1}:</div>
                                <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                        `;
                        for (const [k, v] of Object.entries(item)) {
                            if (v) {
                                multiHtml += `<span class="tag-badge badge-${k}" style="font-size: 11px; padding: 3px 8px;">${translateKey(k)}: <strong>${escapeHtml(String(v))}</strong></span>`;
                            }
                        }
                        multiHtml += `</div></div>`;
                    });

                    multiHtml += `</div></div>`;
                    multiCardPreviewSection.innerHTML = multiHtml;
                    multiCardPreviewSection.style.display = "block";
                } else {
                    multiCardPreviewSection.style.display = "none";
                }
            } else {
                regexMatchStatus.className = "regex-match-status status-box-error";
                regexMatchStatus.textContent = `✗ Error: ${data.message || 'No se pudo generar la expresión regular'}`;
                extractedFieldsJson.textContent = "{}";
                multiCardPreviewSection.style.display = "none";
                btnSaveProvider.disabled = false;
            }
        } catch (err) {
            console.error("Error al generar regex:", err);
            alert("Ocurrió un error al contactar al backend.");
            btnSaveProvider.disabled = false;
        }
    }

    btnSaveProvider.addEventListener("click", async () => {
        let name = provNameInput.value.trim();
        let id = provIdInput.value.trim();
        const format = provFormatSelect.value || "xlsx";
        const rawText = rawTrainText.value.trim();
        
        if (!name) {
            alert("Por favor, introduce un Nombre para el proveedor/competidor.");
            provNameInput.focus();
            return;
        }
        
        if (!id) {
            id = name.toLowerCase()
                .replace(/[^a-z0-9]/g, "_")
                .replace(/_+/g, "_")
                .replace(/^_|_$/g, "");
            provIdInput.value = id;
        }
        
        if (!id) {
            alert("Introduce un ID válido (solo letras, números o guiones bajos).");
            provIdInput.focus();
            return;
        }

        let regex = getGeneratedRegex();
        const hasValidRegex = Boolean(regex && regex !== "^...$" && regex !== ".*");

        if (!rawText && !hasValidRegex) {
            alert("Pega un texto bruto de muestra en 'Texto Bruto de Muestra' o introduce una expresión regular.");
            rawTrainText.focus();
            return;
        }

        // Si no se ha generado la regex todavía o sigue con el placeholder ^...$
        if (!hasValidRegex) {
            // Si no hay etiquetas pero hay texto de muestra, auto-sugerir primero
            if ((!labels || labels.length === 0) && rawText) {
                btnSaveProvider.disabled = true;
                btnSaveProvider.textContent = "⏳ Analizando con IA...";
                try {
                    const resSugg = await fetch("/api/regex/suggest-labels", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ raw_text: rawTrainText.value })
                    });
                    const dataSugg = await resSugg.json();
                    if (dataSugg.status === "success" && dataSugg.labels && dataSugg.labels.length > 0) {
                        labels = dataSugg.labels;
                        labelingWorkspace.style.display = "block";
                        activeTagsSection.style.display = "block";
                        renderInteractiveText();
                    }
                } catch (suggErr) {
                    console.warn("Fallo al auto-sugerir etiquetas:", suggErr);
                }
            }

            if (labels && labels.length > 0 && rawText) {
                try {
                    btnSaveProvider.disabled = true;
                    btnSaveProvider.textContent = "⏳ Generando regex...";
                    const resGen = await fetch("/api/regex/generate", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            raw_text: rawTrainText.value,
                            labels: labels
                        })
                    });
                    const dataGen = await resGen.json();
                    if (dataGen.regex) {
                        regex = dataGen.regex;
                        setGeneratedRegex(regex);
                        regexResultsCard.style.display = "block";
                    }
                } catch (err) {
                    console.warn("Fallo al autogenerar regex, usando fallback básico:", err);
                }
            }
        }

        if (!regex || regex === "^...$") {
            regex = ".*";
        }
        
        // Extraer campos de las etiquetas y de los grupos nombrados del regex
        const fieldsSet = new Set(labels.map(l => l.name));
        const namedGroupMatches = [...regex.matchAll(/\(\?P?<([a-zA-Z_][a-zA-Z0-9_]*)>/g)];
        for (const m of namedGroupMatches) {
            if (m[1]) fieldsSet.add(m[1]);
        }
        const fields = fieldsSet.size > 0 ? Array.from(fieldsSet) : ["product", "model", "price", "attributes"];
        const output_file = `data/extractions/${id}.${format}`;
        
        const providerData = {
            id: id,
            name: name,
            regex: regex,
            fields: fields,
            output_file: output_file,
            file_format: format,
            sample_text: rawTrainText.value,
            labels: labels.map(l => ({
                name: l.name,
                start: parseInt(l.start) || 0,
                end: parseInt(l.end) || 0,
                text: l.text || (rawTrainText.value ? rawTrainText.value.substring(l.start, l.end) : "") || l.name
            }))
        };
        
        btnSaveProvider.disabled = true;
        btnSaveProvider.textContent = "💾 Guardando plantilla...";

        try {
            const res = await fetch("/api/providers", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(providerData)
            });

            if (res.ok) {
                const savedData = await res.json();
                const savedId = savedData.provider?.id || id;
                const finalSavedProv = savedData.provider || providerData;

                // Actualizar inmediatamente en memoria para feedback instantáneo
                const existingIdx = savedProviders.findIndex(p => p.id === savedId);
                if (existingIdx >= 0) {
                    savedProviders[existingIdx] = finalSavedProv;
                } else {
                    savedProviders.push(finalSavedProv);
                }

                // Feedback visual claro en el botón sin borrar el trabajo
                btnSaveProvider.textContent = "✓ ¡Plantilla Guardada!";
                btnSaveProvider.style.background = "#10b981";
                btnSaveProvider.style.color = "#ffffff";
                setTimeout(() => {
                    btnSaveProvider.textContent = "Guardar Proveedor";
                    btnSaveProvider.style.background = "";
                    btnSaveProvider.style.color = "";
                    btnSaveProvider.disabled = false;
                }, 3000);
                
                // Recargar lista y seleccionar/activar automáticamente el proveedor recién guardado
                await loadProviders(savedId);
                await activateProvider(savedId);

                // Mantener el proveedor cargado y visible en el entrenador
                loadProviderIntoTrainer(finalSavedProv);
            } else {
                const errData = await res.json().catch(() => ({}));
                const msg = errData.detail || errData.message || `Error HTTP ${res.status}`;
                alert(`Error al guardar la plantilla en el servidor: ${msg}`);
            }
        } catch (err) {
            console.error("Error guardando proveedor:", err);
            alert(`Error de conexión al intentar guardar la plantilla: ${err.message || err}`);
        } finally {
            btnSaveProvider.disabled = false;
        }
    });

    // Botón para limpiar formulario y crear nueva plantilla
    const btnNewProvider = document.getElementById("btn-new-provider");
    if (btnNewProvider) {
        btnNewProvider.addEventListener("click", () => {
            provNameInput.value = "";
            provIdInput.value = "";
            provIdInput.dataset.autogen = "true";
            provFormatSelect.value = "xlsx";
            rawTrainText.value = "";
            labels = [];
            currentSelection = null;
            
            labelingWorkspace.style.display = "none";
            activeTagsSection.style.display = "none";
            regexResultsCard.style.display = "none";
            setGeneratedRegex("^...$");
            btnSaveProvider.disabled = false;
            provNameInput.focus();
        });
    }

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
        
        const maxDisplayRows = 150;
        const totalRows = result.data.length;
        const displayData = result.data.slice(0, maxDisplayRows);
        
        displayData.forEach(row => {
            const tr = document.createElement("tr");
            
            // Determinar los precios mínimos y máximos sobre Precio Sin IVA
            let minNoVat = Infinity;
            let maxNoVat = -Infinity;
            let noVatCols = [];
            let minVat = Infinity;
            let vatCols = [];
            
            result.columns.forEach(col => {
                if (col.startsWith("Precio ")) {
                    const val = parseFloat(row[col]);
                    if (!isNaN(val) && val > 0) {
                        if (col.includes("Sin IVA")) {
                            noVatCols.push(col);
                            if (val < minNoVat) minNoVat = val;
                            if (val > maxNoVat) maxNoVat = val;
                        } else if (col.includes("Con IVA")) {
                            vatCols.push(col);
                            if (val < minVat) minVat = val;
                        }
                    }
                }
            });
            
            result.columns.forEach(col => {
                if (col.toLowerCase().includes('pvp')) return;
                const td = document.createElement("td");
                const val = row[col];
                
                if (col === "Gama") {
                    let badgeClass = "badge-nd";
                    if (val === "Económica") badgeClass = "badge-eco";
                    else if (val === "Media") badgeClass = "badge-med";
                    else if (val === "Premium") badgeClass = "badge-pre";
                    td.innerHTML = `<span class="${badgeClass}">${val || 'N/D'}</span>`;
                } else {
                    td.textContent = val !== null ? val : "";
                }
                
                // Destacar precio líder (más barato) y el más caro en base a Sin IVA
                if (col.startsWith("Precio ")) {
                    const priceVal = parseFloat(val);
                    if (!isNaN(priceVal) && priceVal > 0) {
                        if (col.includes("Sin IVA") && noVatCols.length > 1) {
                            if (priceVal === minNoVat) {
                                td.className = "highlight-cheap";
                            } else if (priceVal === maxNoVat && maxNoVat > minNoVat) {
                                td.className = "highlight-expensive";
                            }
                        } else if (col.includes("Con IVA") && vatCols.length > 1 && priceVal === minVat) {
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

        if (totalRows > maxDisplayRows) {
            const trNotice = document.createElement("tr");
            trNotice.innerHTML = `
                <td colspan="100%" style="text-align: center; padding: 14px; background: rgba(99, 102, 241, 0.12); color: #c7d2fe; font-size: 13px; font-weight: 500; border-top: 1px solid rgba(99, 102, 241, 0.3);">
                    ✨ <strong>Mostrando 150 de ${totalRows} productos unificados en pantalla.</strong> El archivo completo con todas las comparativas está listo para descargar en Excel pulsando arriba en <em>"📥 Descargar Fichero"</em>.
                </td>
            `;
            mergedResultsBody.appendChild(trNotice);
        }
        
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

    async function sendTextToProcess(text, force = false) {
        if (!activeProviderId) {
            alert("Por favor, selecciona un proveedor activo antes de procesar.");
            return;
        }

        if (!force && isItemDeletedOrSuppressed(text)) {
            lastProcessedClipboard = text;
            console.log("Omitiendo procesamiento regex para ítem recientemente eliminado.");
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

    // ----------------------------------------------------
    // SELECTOR DE MODO DE PORTAPAPELES (IA vs REGEX)
    // ----------------------------------------------------
    let currentClipboardMode = localStorage.getItem("garde_clipboard_mode") || "gemini";

    function updateClipboardModeUI() {
        if (currentClipboardMode === "gemini") {
            if (btnModeGemini) {
                btnModeGemini.style.background = "#4f46e5";
                btnModeGemini.style.color = "#ffffff";
                btnModeGemini.style.fontWeight = "600";
            }
            if (btnModeRegex) {
                btnModeRegex.style.background = "transparent";
                btnModeRegex.style.color = "var(--text-muted)";
                btnModeRegex.style.fontWeight = "500";
            }
            if (clipboardModeBadge) {
                clipboardModeBadge.textContent = "🤖 Modo: IA Gemini";
                clipboardModeBadge.className = "badge badge-success";
            }
            if (clipboardModeDesc) {
                clipboardModeDesc.innerHTML = "✨ <strong>Modo IA Activo:</strong> El monitoreo automático y las capturas extraerán <em>Tipo de Aparato, Marca, Modelo, Descripción y Precios</em> estándar para comparar en Excel.";
                clipboardModeDesc.style.borderLeftColor = "#6366f1";
                clipboardModeDesc.style.color = "#c7d2fe";
            }
            if (btnExtractTextAi) {
                btnExtractTextAi.className = "btn btn-primary";
            }
            if (btnPasteClipboard) {
                btnPasteClipboard.className = "btn btn-secondary";
            }
        } else {
            if (btnModeGemini) {
                btnModeGemini.style.background = "transparent";
                btnModeGemini.style.color = "var(--text-muted)";
                btnModeGemini.style.fontWeight = "500";
            }
            if (btnModeRegex) {
                btnModeRegex.style.background = "#0284c7";
                btnModeRegex.style.color = "#ffffff";
                btnModeRegex.style.fontWeight = "600";
            }
            if (clipboardModeBadge) {
                clipboardModeBadge.textContent = "🎯 Modo: Plantilla Regex";
                clipboardModeBadge.className = "badge badge-info";
            }
            if (clipboardModeDesc) {
                clipboardModeDesc.innerHTML = "🎯 <strong>Modo Regex Activo:</strong> El monitoreo automático y las capturas aplicarán la regla regex y etiquetas específicas configuradas para esta tienda.";
                clipboardModeDesc.style.borderLeftColor = "#0284c7";
                clipboardModeDesc.style.color = "#bae6fd";
            }
            if (btnExtractTextAi) {
                btnExtractTextAi.className = "btn btn-secondary";
            }
            if (btnPasteClipboard) {
                btnPasteClipboard.className = "btn btn-primary";
            }
        }
    }

    if (btnModeGemini) {
        btnModeGemini.addEventListener("click", () => {
            currentClipboardMode = "gemini";
            localStorage.setItem("garde_clipboard_mode", "gemini");
            updateClipboardModeUI();
        });
    }

    if (btnModeRegex) {
        btnModeRegex.addEventListener("click", () => {
            currentClipboardMode = "regex";
            localStorage.setItem("garde_clipboard_mode", "regex");
            updateClipboardModeUI();
        });
    }

    // Inicializar visualmente el modo seleccionado
    updateClipboardModeUI();

    async function processTextWithAi(text, force = false) {
        if (suppressClipboardAutoCheck) {
            return;
        }
        if (!activeProviderId) {
            alert("Por favor, selecciona un proveedor activo antes de extraer con IA.");
            return;
        }

        const trimmed = (text || "").trim();
        if (!trimmed) return;

        if (!force && isItemDeletedOrSuppressed(trimmed)) {
            lastProcessedClipboard = trimmed;
            console.log("Texto pertenece a un ítem recientemente eliminado. Omitiendo petición Gemini para ahorrar tokens.");
            return;
        }

        // Comprobación anti-bucle / duplicados en frontend (10 minutos)
        const now = Date.now();
        const cacheKey = `${activeProviderId}::${trimmed}`;
        if (recentAiSentTexts.has(cacheKey) && (now - recentAiSentTexts.get(cacheKey) < 600000)) {
            console.log("Texto idéntico procesado recientemente con Gemini. Omitiendo re-petición para ahorrar tokens.");
            return;
        }

        lastProcessedClipboard = trimmed;
        recentAiSentTexts.set(cacheKey, now);
        if (recentAiSentTexts.size > 150) {
            const firstKey = recentAiSentTexts.keys().next().value;
            recentAiSentTexts.delete(firstKey);
        }

        if (btnExtractTextAi) {
            btnExtractTextAi.disabled = true;
            btnExtractTextAi.innerHTML = '⏳ Extrayendo con IA...';
        }

        appendLog({
            timestamp: new Date().toLocaleTimeString(),
            type: "info",
            message: "Enviando texto a Google Gemini para extracción estructurada directa..."
        });

        try {
            const res = await fetch("/api/process-text-ai", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: trimmed, provider_id: activeProviderId })
            });
            const data = await res.json();
            if (res.ok && data.status === "success") {
                const count = data.count || (data.items ? data.items.length : 0);
                appendLog({
                    timestamp: new Date().toLocaleTimeString(),
                    type: "success",
                    message: `IA Gemini extrajo y guardó con éxito ${count} producto(s) en columnas universales.`
                });
                if (pasteInputArea) pasteInputArea.value = "";
                await loadRecentCaptures();
            } else {
                appendLog({
                    timestamp: new Date().toLocaleTimeString(),
                    type: "error",
                    message: `Error en extracción con IA: ${data.detail || 'Fallo desconocido'}`
                });
                alert(`Error en extracción con IA: ${data.detail || 'Fallo desconocido'}`);
            }
        } catch (err) {
            appendLog({
                timestamp: new Date().toLocaleTimeString(),
                type: "error",
                message: `Error de conexión con Gemini: ${err.message}`
            });
        } finally {
            if (btnExtractTextAi) {
                btnExtractTextAi.disabled = false;
                btnExtractTextAi.innerHTML = `
                    <span style="font-size: 12px; font-weight: 700;">🤖 Extraer con IA</span>
                    <span style="font-size: 10px; opacity: 0.85; margin-top: 2px;">Columnas comparables</span>
                `;
            }
        }
    }

    function routeClipboardText(text) {
        if (suppressClipboardAutoCheck) return;
        if (!text || !text.trim()) return;
        const clean = text.trim();
        if (isItemDeletedOrSuppressed(clean)) {
            lastProcessedClipboard = clean;
            console.log("Portapapeles coincide con un ítem recientemente eliminado. Omitiendo petición para ahorrar tokens.");
            return;
        }
        if (currentClipboardMode === "gemini") {
            processTextWithAi(clean);
        } else {
            sendTextToProcess(clean);
        }
    }

    // Auto-leer portapapeles cuando la pestaña/ventana recupera el enfoque
    async function checkClipboardOnFocus() {
        if (suppressClipboardAutoCheck) {
            return;
        }
        if (!monitorToggle.checked || !activeProviderId) {
            return;
        }
        
        if (!navigator.clipboard || !navigator.clipboard.readText) {
            return;
        }
        
        try {
            const text = await navigator.clipboard.readText();
            if (text && text.trim()) {
                const clean = text.trim();
                if (isItemDeletedOrSuppressed(clean)) {
                    lastProcessedClipboard = clean;
                    return;
                }
                if (clean !== lastProcessedClipboard) {
                    routeClipboardText(clean);
                }
            }
        } catch (err) {
            console.log("No se pudo auto-leer el portapapeles al enfocar:", err);
        }
    }

    // Eventos de foco y visibilidad
    window.addEventListener("focus", checkClipboardOnFocus);
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            checkClipboardOnFocus();
        }
    });

    // Interceptar Ctrl+V global en el documento
    document.addEventListener("paste", (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        const text = e.clipboardData.getData("text");
        if (text && text.trim()) {
            routeClipboardText(text);
        }
    });

    // Botón manual: Forzar extracción con Regex
    btnPasteClipboard.addEventListener("click", async () => {
        let text = pasteInputArea ? pasteInputArea.value.trim() : "";
        if (!text) {
            if (navigator.clipboard && navigator.clipboard.readText) {
                try {
                    text = (await navigator.clipboard.readText()).trim();
                } catch (err) {
                    alert("No se pudo acceder al portapapeles. Asegúrate de dar permisos en el navegador o pega el texto en la caja.");
                    return;
                }
            } else {
                alert("El portapapeles no está disponible. Pega el texto directamente en la caja.");
                return;
            }
        }
        if (text) {
            sendTextToProcess(text, true);
            if (pasteInputArea) pasteInputArea.value = "";
        } else {
            alert("No hay texto copiado en el portapapeles ni en la caja de pegado rápido.");
        }
    });

    // Botón manual: Forzar extracción con IA Gemini
    if (btnExtractTextAi) {
        btnExtractTextAi.addEventListener("click", async () => {
            let text = pasteInputArea ? pasteInputArea.value.trim() : "";
            if (!text) {
                if (navigator.clipboard && navigator.clipboard.readText) {
                    try {
                        text = (await navigator.clipboard.readText()).trim();
                    } catch (err) {
                        console.warn("No se pudo leer automáticamente del portapapeles:", err);
                    }
                }
            }
            if (!text) {
                alert("Pega texto en la 'Caja de Pegado Rápido' o copia texto al portapapeles antes de pulsar 'Extraer con IA'.");
                return;
            }
            await processTextWithAi(text, true);
        });
    }

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
    const stockColorSelect = document.getElementById("stock-color-select");
    const btnClearStock = document.getElementById("btn-clear-stock");
    const btnExportStockXlsx = document.getElementById("btn-export-stock-xlsx");
    const stockCoveragePctBadge = document.getElementById("stock-coverage-pct-badge");
    const btnConfigureLimits = document.getElementById("btn-configure-limits");
    
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

    // currentStockData is declared at the top scope

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

    async function loadStockMatrix(selectedCategory = "", selectedColor = "") {
        try {
            let url = "/api/stock/matrix";
            const params = [];
            if (selectedCategory) params.push(`category=${encodeURIComponent(selectedCategory)}`);
            if (selectedColor) params.push(`color=${encodeURIComponent(selectedColor)}`);
            if (params.length > 0) {
                url += "?" + params.join("&");
            }
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

            if (btnConfigureLimits) {
                btnConfigureLimits.disabled = !data.categories || data.categories.length === 0;
            }

            // 1.5 Rellenar selector de colores
            populateColorSelect(data.colors_available || [], data.selected_color || "");

            // 2. Pintar KPIs
            kpiStockValue.textContent = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(data.kpis.total_value);
            kpiStockRefs.textContent = data.kpis.total_references;
            kpiStockQty.textContent = data.kpis.total_stock;
            stockCoveragePctBadge.textContent = `Cobertura: ${data.kpis.coverage_pct}%`;

            // 3. Pintar Alertas / Huecos de catálogo
            stockAlertsList.innerHTML = "";
            if (data.alerts && data.alerts.length > 0) {
                data.alerts.forEach(alertItem => {
                    const box = document.createElement("div");
                    box.className = `alert-box-${alertItem.type === 'danger' ? 'error' : (alertItem.type === 'warning' ? 'warning' : 'info')}`;
                    box.style.margin = "0";
                    box.style.fontSize = "12px";
                    box.textContent = alertItem.message;
                    stockAlertsList.appendChild(box);
                });
            } else {
                stockAlertsList.innerHTML = `<div class="alert-box-success" style="margin:0; font-size:12px;">¡Felicidades! Tienes cobertura del 100% en todos los segmentos.</div>`;
            }

            // Ocultar detalles previos
            stockCellDetailsCard.style.display = "none";
            stockMarketCompCard.style.display = "none";

            const stockBrandList = document.getElementById("stock-brand-breakdown-list");

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

            // Llamar al renderizador de la matriz
            renderStockMatrixTable();

        } catch (err) {
            console.error("Error cargando matriz:", err);
        }
    }

    function populateColorSelect(colors, selectedColor) {
        if (!stockColorSelect) return;
        const activeColor = selectedColor || stockColorSelect.value || "";
        
        stockColorSelect.innerHTML = "";
        
        const defaultOpt = document.createElement("option");
        defaultOpt.value = "";
        defaultOpt.textContent = "-- Todos los colores --";
        if (activeColor === "") {
            defaultOpt.selected = true;
        }
        stockColorSelect.appendChild(defaultOpt);
        
        colors.forEach(col => {
            if (!col) return;
            const opt = document.createElement("option");
            opt.value = col;
            opt.textContent = col;
            if (col === activeColor) {
                opt.selected = true;
            }
            stockColorSelect.appendChild(opt);
        });
    }

    function renderStockMatrixTable() {
        // matrixHeaders, matrixBody ya declarados en el scope padre (líneas 1459-1460)
        const stockBrandList = document.getElementById("stock-brand-breakdown-list");

        if (!currentStockData || !currentStockData.capacities || currentStockData.capacities.length === 0) {
            matrixHeaders.innerHTML = "";
            matrixBody.innerHTML = `<tr><td class="table-empty" style="padding: 40px; text-align: center; color: var(--text-muted);">Sube el PDF valorado de tu almacén para generar la matriz de stock.</td></tr>`;
            if (stockBrandList) {
                stockBrandList.innerHTML = `<p style="font-size: 11px; color: var(--text-muted);">Sube el stock para ver la distribución.</p>`;
            }
            return;
        }

        // Obtener filtros
        const filterInput = document.getElementById("matrix-col-filter");
        const filterText = filterInput ? filterInput.value.trim().toLowerCase() : "";
        const activeBtns = document.querySelectorAll(".matrix-quick-filter.active");
        const activeFilters = Array.from(activeBtns).map(btn => btn.dataset.filter);

        let filteredCapacities = [...currentStockData.capacities];

        // Aplicar filtros rápidos acumulativos (si no está seleccionado 'all')
        if (activeFilters.length > 0 && !activeFilters.includes("all")) {
            filteredCapacities = filteredCapacities.filter(cap => {
                const c = cap.toLowerCase();
                return activeFilters.some(filter => {
                    if (filter === "medidas") {
                        return /\d+\s*[Xx]\s*\d+/.test(c);
                    } else if (filter === "kilos") {
                        return /(?:\b\d+\s*|\b)(?:kg|kilos|k)\b/.test(c);
                    } else if (filter === "litros") {
                        return /(?:\b\d+\s*|\b)(?:l|litros|lts)\b/.test(c) && !/(?:\b\d+\s*|\b)(?:kg|kilos|k)\b/.test(c) && !/\d+\s*[Xx]\s*\d+/.test(c);
                    } else if (filter === "caracteristicas") {
                        return !/\d+\s*[Xx]\s*\d+/.test(c) && !/(?:\b\d+\s*|\b)(?:kg|kilos|k)\b/.test(c) && !/(?:\b\d+\s*|\b)(?:l|litros|lts)\b/.test(c) && c !== "n/d";
                    }
                    return false;
                });
            });
        }

        // Aplicar filtro de texto
        if (filterText) {
            filteredCapacities = filteredCapacities.filter(cap => cap.toLowerCase().includes(filterText));
        }

        if (filteredCapacities.length === 0) {
            matrixHeaders.innerHTML = "<th>Marca / Capacidad</th>";
            matrixBody.innerHTML = `<tr><td colspan="100%" class="table-empty" style="padding: 40px; text-align: center; color: var(--text-muted);">Ninguna columna coincide con los filtros aplicados.</td></tr>`;
            return;
        }

        // Render Headers (Capacidades)
        matrixHeaders.innerHTML = "<th>Marca / Capacidad</th>";
        filteredCapacities.forEach(cap => {
            const th = document.createElement("th");
            th.textContent = cap;
            matrixHeaders.appendChild(th);
        });

        // Render Rows (Marcas)
        matrixBody.innerHTML = "";
        currentStockData.brands.forEach(br => {
            const tr = document.createElement("tr");
            
            // Celda de etiqueta de la fila (Marca)
            const tdLabel = document.createElement("td");
            tdLabel.className = "matrix-row-label";
            tdLabel.textContent = br;
            tr.appendChild(tdLabel);
            
            // Celdas de cruce (capacidad)
            filteredCapacities.forEach(cap => {
                const cellData = currentStockData.cells.find(c => c.capacity === cap && c.brand === br);
                const td = document.createElement("td");
                td.className = `matrix-cell-interactive`;
                
                if (!cellData || cellData.count === 0) {
                    td.style.background = "rgba(255,255,255,0.01)";
                }
                
                if (cellData) {
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
                        badge.textContent = `${key}: ${seg.stock}`;
                        badge.title = `${segmentLabels[key]}: ${seg.count} referencias (${seg.stock} uds en stock)`;
                        
                        badge.addEventListener("click", (event) => {
                            event.stopPropagation(); // Evitar disparar el click de la celda completa
                            document.querySelectorAll(".segment-badge").forEach(b => b.classList.remove("selected-badge"));
                            document.querySelectorAll(".matrix-cell-interactive").forEach(c => c.classList.remove("selected-cell"));
                            badge.classList.add("selected-badge");
                            showSegmentCellDetails(cellData, key, segmentLabels[key]);
                        });
                        
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
                        // Resaltar celda seleccionada y limpiar badges
                        document.querySelectorAll(".matrix-cell-interactive").forEach(c => c.classList.remove("selected-cell"));
                        document.querySelectorAll(".segment-badge").forEach(b => b.classList.remove("selected-badge"));
                        td.classList.add("selected-cell");
                        showCellDetails(cellData);
                    });
                } else {
                    td.textContent = "—";
                }
                
                tr.appendChild(td);
            });
            
            matrixBody.appendChild(tr);
        });
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

    function showSegmentCellDetails(cellData, segmentKey, labelName) {
        stockCellDetailsCard.style.display = "block";
        stockMarketCompCard.style.display = "none";
        
        stockDetailsTitle.textContent = `Referencias de '${cellData.brand}' en ${cellData.capacity} (${labelName})`;
        
        stockDetailsBody.innerHTML = "";
        const segProducts = cellData.segments[segmentKey].products || [];
        if (segProducts.length === 0) {
            stockDetailsBody.innerHTML = `<tr><td colspan="100%" class="table-empty">No hay productos en esta gama para este cruce.</td></tr>`;
            return;
        }

        segProducts.forEach(p => {
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
        // Al cambiar de categoría, limpiar los filtros de la interfaz
        const filterInput = document.getElementById("matrix-col-filter");
        if (filterInput) filterInput.value = "";
        document.querySelectorAll(".matrix-quick-filter").forEach(b => b.classList.remove("active"));
        const allBtn = document.querySelector(".matrix-quick-filter[data-filter='all']");
        if (allBtn) allBtn.classList.add("active");
        
        // Resetear selector de color
        if (stockColorSelect) stockColorSelect.value = "";
        
        loadStockMatrix(stockCategorySelect.value, "");
    });

    if (stockColorSelect) {
        stockColorSelect.addEventListener("change", () => {
            loadStockMatrix(stockCategorySelect.value, stockColorSelect.value);
        });
    }

    if (btnExportStockXlsx) {
        btnExportStockXlsx.addEventListener("click", () => {
            const cat = stockCategorySelect.value || "";
            const color = stockColorSelect ? stockColorSelect.value : "";
            let url = `/api/stock/export/xlsx`;
            const params = [];
            if (cat) params.push(`category=${encodeURIComponent(cat)}`);
            if (color) params.push(`color=${encodeURIComponent(color)}`);
            if (params.length > 0) {
                url += "?" + params.join("&");
            }
            window.open(url, "_blank");
        });
    }

    // Filtros de columnas de la matriz
    const matrixColFilterInput = document.getElementById("matrix-col-filter");
    if (matrixColFilterInput) {
        matrixColFilterInput.addEventListener("input", () => {
            renderStockMatrixTable();
        });
    }

    const quickFiltersContainer = document.getElementById("matrix-quick-filters");
    if (quickFiltersContainer) {
        quickFiltersContainer.addEventListener("click", (e) => {
            const btn = e.target.closest(".matrix-quick-filter");
            if (btn) {
                const filterType = btn.dataset.filter;
                if (filterType === "all") {
                    document.querySelectorAll(".matrix-quick-filter").forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                } else {
                    const allBtn = document.querySelector(".matrix-quick-filter[data-filter='all']");
                    if (allBtn) allBtn.classList.remove("active");
                    
                    btn.classList.toggle("active");
                    
                    // Si no queda ninguno activo, activar 'all'
                    const activeFilters = document.querySelectorAll(".matrix-quick-filter.active");
                    if (activeFilters.length === 0 && allBtn) {
                        allBtn.classList.add("active");
                    }
                }
                renderStockMatrixTable();
            }
        });
    }

    // MODAL DE AJUSTE DE GAMAS (LÍMITES DE PRECIO)
    const modalLimits = document.getElementById("modal-limits");
    const btnCloseModalLimits = document.getElementById("btn-close-modal-limits");
    const btnCancelLimits = document.getElementById("btn-cancel-limits");
    const btnSaveLimits = document.getElementById("btn-save-limits");
    const inputLimitEco = document.getElementById("input-limit-eco");
    const inputLimitMed = document.getElementById("input-limit-med");
    const modalCategoryName = document.getElementById("modal-category-name");
    const modalMedStartLabel = document.getElementById("modal-med-start-label");
    const modalPremiumStart = document.getElementById("modal-premium-start");

    if (btnConfigureLimits && modalLimits) {
        btnConfigureLimits.addEventListener("click", async () => {
            const category = stockCategorySelect.value;
            if (!category) return;

            try {
                const res = await fetch(`/api/stock/price-limits?category=${encodeURIComponent(category)}`);
                if (res.ok) {
                    const data = await res.json();
                    modalCategoryName.textContent = category;
                    inputLimitEco.value = data.eco_max;
                    inputLimitMed.value = data.med_max;

                    // Trigger helper text updates
                    updateModalLabels();

                    modalLimits.style.display = "flex";
                } else {
                    alert("Error al cargar los límites de precio.");
                }
            } catch (err) {
                console.error("Error al obtener límites:", err);
                alert("Error de conexión al obtener límites.");
            }
        });

        const closeModal = () => {
            modalLimits.style.display = "none";
        };

        if (btnCloseModalLimits) btnCloseModalLimits.addEventListener("click", closeModal);
        if (btnCancelLimits) btnCancelLimits.addEventListener("click", closeModal);

        // Close on clicking outside the modal content
        modalLimits.addEventListener("click", (e) => {
            if (e.target === modalLimits) {
                closeModal();
            }
        });

        // Helper calculations inside the modal
        function updateModalLabels() {
            const ecoVal = parseFloat(inputLimitEco.value) || 0;
            const medVal = parseFloat(inputLimitMed.value) || 0;
            if (modalMedStartLabel) modalMedStartLabel.textContent = `Desde ${ecoVal} € hasta`;
            if (modalPremiumStart) modalPremiumStart.textContent = `${medVal} €`;
        }

        if (inputLimitEco) {
            inputLimitEco.addEventListener("input", updateModalLabels);
            inputLimitEco.addEventListener("change", updateModalLabels);
        }
        if (inputLimitMed) {
            inputLimitMed.addEventListener("input", updateModalLabels);
            inputLimitMed.addEventListener("change", updateModalLabels);
        }

        if (btnSaveLimits) {
            btnSaveLimits.addEventListener("click", async () => {
                const category = stockCategorySelect.value;
                const eco_max = parseFloat(inputLimitEco.value) || 0;
                const med_max = parseFloat(inputLimitMed.value) || 0;

                if (eco_max <= 0 || med_max <= eco_max) {
                    alert("El límite Económico debe ser mayor a cero, y el límite Medio debe ser estrictamente mayor que el Económico.");
                    return;
                }

                try {
                    const res = await fetch("/api/stock/price-limits", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            category: category,
                            eco_max: eco_max,
                            med_max: med_max
                        })
                    });

                    if (res.ok) {
                        closeModal();
                        // Volver a cargar la matriz
                        loadStockMatrix(category, stockColorSelect ? stockColorSelect.value : "");
                    } else {
                        const errData = await res.json();
                        alert(`Error al guardar límites: ${errData.detail || "Verifica los valores."}`);
                    }
                } catch (err) {
                    console.error("Error guardando límites:", err);
                    alert("Error al conectar con el servidor.");
                }
            });
        }
    }

    if (btnClearStock) {
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
    }

    // --- Gestión de Configuración de Gemini AI ---
    async function loadGeminiConfig() {
        try {
            const res = await fetch("/api/gemini-config");
            if (res.ok) {
                const data = await res.json();
                if (imageEngineSelect && data.image_engine) {
                    imageEngineSelect.value = data.image_engine;
                }
                if (geminiFallbackCheckbox && data.gemini_auto_fallback !== undefined) {
                    geminiFallbackCheckbox.checked = Boolean(data.gemini_auto_fallback);
                }
                if (geminiKeyStatus) {
                    if (data.has_key) {
                        geminiKeyStatus.textContent = "✨ Gemini Conectado";
                        geminiKeyStatus.className = "badge badge-success";
                        geminiKeyStatus.title = `Clave activa (${data.key_preview || 'Configurada'})`;
                        if (geminiApiKeyInput) {
                            geminiApiKeyInput.placeholder = `Clave guardada: ${data.key_preview || '***'}`;
                        }
                    } else {
                        geminiKeyStatus.textContent = "⚠️ Sin Clave API";
                        geminiKeyStatus.className = "badge badge-warning";
                        geminiKeyStatus.title = "Haz clic en '⚙️ Clave' para añadir tu API key";
                    }
                }
            }
        } catch (e) {
            console.warn("Error cargando configuración de Gemini:", e);
        }
    }

    if (geminiFallbackCheckbox) {
        geminiFallbackCheckbox.addEventListener("change", async () => {
            const val = geminiFallbackCheckbox.checked;
            try {
                await fetch("/api/gemini-config", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ gemini_auto_fallback: val })
                });
                appendLog({
                    timestamp: new Date().toLocaleTimeString(),
                    type: "info",
                    message: `Modo Rescate IA Gemini en portapapeles: ${val ? 'Activado' : 'Desactivado'}`
                });
            } catch (e) {
                console.error("Error actualizando modo rescate Gemini:", e);
            }
        });
    }



    if (imageEngineSelect) {
        imageEngineSelect.addEventListener("change", async () => {
            const val = imageEngineSelect.value;
            try {
                await fetch("/api/gemini-config", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ image_engine: val })
                });
                appendLog({
                    timestamp: new Date().toLocaleTimeString(),
                    type: "info",
                    message: `Motor de análisis de imagen cambiado a: ${val === 'gemini' ? 'IA Gemini' : 'OCR Local'}`
                });
            } catch (e) {
                console.error(e);
            }
        });
    }

    if (btnConfigGemini) {
        btnConfigGemini.addEventListener("click", () => {
            if (geminiConfigCard) {
                geminiConfigCard.style.display = geminiConfigCard.style.display === "none" ? "block" : "none";
            }
        });
    }

    if (geminiKeyStatus) {
        geminiKeyStatus.addEventListener("click", () => {
            if (geminiConfigCard) {
                geminiConfigCard.style.display = "block";
            }
        });
    }

    if (btnCloseGeminiConfig) {
        btnCloseGeminiConfig.addEventListener("click", () => {
            if (geminiConfigCard) geminiConfigCard.style.display = "none";
        });
    }

    if (btnToggleShowKey && geminiApiKeyInput) {
        btnToggleShowKey.addEventListener("click", () => {
            geminiApiKeyInput.type = geminiApiKeyInput.type === "password" ? "text" : "password";
        });
    }

    if (btnSaveGeminiKey && geminiApiKeyInput) {
        btnSaveGeminiKey.addEventListener("click", async () => {
            const keyVal = geminiApiKeyInput.value.trim();
            if (!keyVal) {
                if (geminiConfigMsg) {
                    geminiConfigMsg.textContent = "⚠️ Introduce una clave válida.";
                    geminiConfigMsg.style.color = "#f59e0b";
                }
                return;
            }
            try {
                const res = await fetch("/api/gemini-config", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ gemini_api_key: keyVal })
                });
                if (res.ok) {
                    if (geminiConfigMsg) {
                        geminiConfigMsg.textContent = "✅ Clave API guardada correctamente.";
                        geminiConfigMsg.style.color = "#10b981";
                    }
                    geminiApiKeyInput.value = "";
                    loadGeminiConfig();
                    setTimeout(() => {
                        if (geminiConfigCard) geminiConfigCard.style.display = "none";
                        if (geminiConfigMsg) geminiConfigMsg.textContent = "";
                    }, 1500);
                }
            } catch (err) {
                if (geminiConfigMsg) {
                    geminiConfigMsg.textContent = "❌ Error guardando la clave.";
                    geminiConfigMsg.style.color = "#ef4444";
                }
            }
        });
    }

    // ─────────────────────────────────────────────────────────────────────────
    // MÓDULO: AUDITORÍA DE FALTAS, COMPARADOR DE TARIFAS Y ANÁLISIS DE VENTAS IA
    // ─────────────────────────────────────────────────────────────────────────
    let auditShortagesData = null;
    let auditDeltaData = null;

    // Elementos del DOM de Auditoría
    const selectAuditSnapshot = document.getElementById("select-audit-snapshot");
    const selectAuditProvider = document.getElementById("select-audit-provider");
    const selectAuditBrand = document.getElementById("select-audit-brand");
    const inputAuditThreshold = document.getElementById("input-audit-threshold");
    const btnRunAudit = document.getElementById("btn-run-audit");
    const btnUploadAuditPdf = document.getElementById("btn-upload-audit-pdf");
    const auditFileInput = document.getElementById("audit-file-input");
    const auditManualDate = document.getElementById("audit-manual-date");
    const snapshotMetaInfo = document.getElementById("snapshot-meta-info");

    // Elementos del Gestor de Tarifas de Proveedor (PDF o Excel)
    const tariffFileInput = document.getElementById("tariff-file-input");
    const tariffProviderInput = document.getElementById("tariff-provider-input");
    const tariffNameInput = document.getElementById("tariff-name-input");
    const btnUploadTariff = document.getElementById("btn-upload-tariff");
    const tariffsListContainer = document.getElementById("tariffs-list-container");

    const selectDeltaOld = document.getElementById("select-delta-old");
    const selectDeltaNew = document.getElementById("select-delta-new");
    const btnRunSalesDelta = document.getElementById("btn-run-sales-delta");

    const btnTriggerGemini = document.getElementById("btn-trigger-gemini-ai");
    const cardGeminiExec = document.getElementById("card-gemini-executive");
    const geminiReportContent = document.getElementById("gemini-report-body");
    const btnCloseGeminiCard = document.getElementById("btn-close-gemini-card");

    const btnExportAuditXlsx = document.getElementById("btn-export-audit-excel");

    // Sub-pestañas de tablas
    const auditSubtabBtns = document.querySelectorAll(".audit-subtab-btn");
    auditSubtabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            auditSubtabBtns.forEach(b => {
                b.classList.remove("active");
                b.classList.add("btn-secondary");
            });
            document.querySelectorAll(".audit-subtab-content").forEach(c => c.style.display = "none");
            btn.classList.add("active");
            btn.classList.remove("btn-secondary");
            const targetEl = document.getElementById(btn.dataset.subtab);
            if (targetEl) targetEl.style.display = "block";
        });
    });

    if (btnCloseGeminiCard && cardGeminiExec) {
        btnCloseGeminiCard.addEventListener("click", () => {
            cardGeminiExec.style.display = "none";
        });
    }

    async function initAuditTab() {
        await loadSavedTariffs();
        await loadAuditSnapshots();
        await loadAuditBrands();
    }

    // Cargar tarifas registradas en data/tariffs/ y actualizar tanto la lista visual como el selector de cruce
    async function loadSavedTariffs(selectedTariffId = null) {
        if (!tariffsListContainer && !selectAuditProvider) return;
        try {
            const res = await fetch("/api/tariffs/list");
            const tariffs = await res.json();

            // 1. Renderizar lista en la tarjeta de Tarifas
            if (tariffsListContainer) {
                tariffsListContainer.innerHTML = "";
                if (!tariffs || tariffs.length === 0) {
                    tariffsListContainer.innerHTML = `
                        <div style="font-size: 11px; color: var(--text-muted); padding: 12px; text-align: center;">
                            No hay tarifas registradas todavía.<br>Sube una arriba en PDF o Excel (.xlsx, .xls, .csv).
                        </div>`;
                } else {
                    tariffs.forEach(t => {
                        const row = document.createElement("div");
                        row.style.display = "flex";
                        row.style.justifyContent = "space-between";
                        row.style.alignItems = "center";
                        row.style.padding = "6px 8px";
                        row.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
                        row.style.gap = "8px";

                        const isPdf = (t.file_type || '').toLowerCase() === 'pdf';
                        const badgeColor = isPdf ? '#ef4444' : '#10b981';
                        const badgeBg = isPdf ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)';

                        row.innerHTML = `
                            <div style="display: flex; align-items: center; gap: 6px; overflow: hidden;">
                                <span style="font-size: 9px; font-weight: 700; background: ${badgeBg}; color: ${badgeColor}; padding: 2px 5px; border-radius: 4px; text-transform: uppercase;">
                                    ${escapeHtml(t.file_type || 'DOC')}
                                </span>
                                <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                    <strong style="font-size: 12px; color: var(--text-main);">${escapeHtml(t.provider_name)}</strong>
                                    <span style="font-size: 11px; color: var(--text-muted);"> · ${escapeHtml(t.tariff_name)}</span>
                                    <span style="font-size: 10px; color: var(--text-muted); display: block;">${t.total_items} refs • ${t.upload_date}</span>
                                </div>
                            </div>
                            <div style="display: flex; gap: 4px; align-items: center;">
                                <button class="btn btn-secondary btn-sm btn-select-tariff" data-id="${escapeHtml(t.id)}" style="font-size: 10px; padding: 2px 6px;" title="Seleccionar para el cruce de auditoría">
                                    Usar
                                </button>
                                <button class="btn btn-secondary btn-sm btn-delete-tariff" data-id="${escapeHtml(t.id)}" style="font-size: 10px; padding: 2px 6px; color: #ef4444;" title="Eliminar tarifa">
                                    🗑️
                                </button>
                            </div>
                        `;
                        tariffsListContainer.appendChild(row);
                    });

                    // Event listeners para 'Usar' y 'Eliminar'
                    tariffsListContainer.querySelectorAll(".btn-select-tariff").forEach(btn => {
                        btn.addEventListener("click", (e) => {
                            const tid = e.currentTarget.dataset.id;
                            if (selectAuditProvider) {
                                selectAuditProvider.value = tid;
                                selectAuditProvider.focus();
                                selectAuditProvider.style.outline = "2px solid #6c5ce7";
                                setTimeout(() => { selectAuditProvider.style.outline = ""; }, 1200);
                            }
                        });
                    });

                    tariffsListContainer.querySelectorAll(".btn-delete-tariff").forEach(btn => {
                        btn.addEventListener("click", async (e) => {
                            const tid = e.currentTarget.dataset.id;
                            if (confirm("¿Seguro que deseas eliminar esta tarifa guardada?")) {
                                try {
                                    const delRes = await fetch(`/api/tariffs/${encodeURIComponent(tid)}`, { method: "DELETE" });
                                    if (delRes.ok) {
                                        await loadSavedTariffs();
                                    } else {
                                        alert("Error eliminando tarifa.");
                                    }
                                } catch (err) {
                                    alert(`Error al eliminar: ${err.message}`);
                                }
                            }
                        });
                    });
                }
            }

            // 2. Poblar el selector de cruce selectAuditProvider
            if (selectAuditProvider) {
                const prevVal = selectedTariffId || selectAuditProvider.value;
                selectAuditProvider.innerHTML = "";

                if (tariffs && tariffs.length > 0) {
                    const grpTariffs = document.createElement("optgroup");
                    grpTariffs.label = "Catálogos y Listas de Proveedores Guardadas";
                    tariffs.forEach(t => {
                        const opt = document.createElement("option");
                        opt.value = t.id;
                        opt.textContent = `📁 [${(t.file_type || '').toUpperCase()}] ${t.provider_name} - ${t.tariff_name} (${t.total_items} referencias)`;
                        grpTariffs.appendChild(opt);
                    });
                    selectAuditProvider.appendChild(grpTariffs);
                }

                // Cargar también archivos de extractions como fallback histórico
                try {
                    const extRes = await fetch("/api/extractions/files");
                    const extFiles = await extRes.json();
                    if (extFiles && extFiles.length > 0) {
                        const grpExtractions = document.createElement("optgroup");
                        grpExtractions.label = "Archivos de Catálogos Anteriores";
                        extFiles.forEach(f => {
                            const opt = document.createElement("option");
                            opt.value = f.filename;
                            opt.textContent = `📄 ${f.filename} (${f.last_modified})`;
                            grpExtractions.appendChild(opt);
                        });
                        selectAuditProvider.appendChild(grpExtractions);
                    }
                } catch (e_ext) {
                    // ignorar fallback si falla
                }

                if (!selectAuditProvider.children.length) {
                    selectAuditProvider.innerHTML = '<option value="">-- No hay tarifas disponibles --</option>';
                } else if (prevVal) {
                    selectAuditProvider.value = prevVal;
                }
            }
        } catch (err) {
            console.error("Error cargando tarifas registradas:", err);
        }
    }

    // Subida de Tarifa de Proveedor (PDF o Excel)
    if (btnUploadTariff && tariffFileInput) {
        btnUploadTariff.addEventListener("click", async () => {
            if (!tariffFileInput.files || tariffFileInput.files.length === 0) {
                alert("Por favor selecciona un archivo de tarifa (PDF o Excel .xlsx, .xls, .csv).");
                return;
            }
            const provName = (tariffProviderInput?.value || "").trim();
            if (!provName) {
                alert("Por favor indica el Nombre del Proveedor (ej. Balay, Bosch, Teka...).");
                tariffProviderInput?.focus();
                return;
            }
            const tName = (tariffNameInput?.value || "").trim() || `Tarifa ${new Date().toLocaleDateString('es-ES')}`;

            const file = tariffFileInput.files[0];
            const formData = new FormData();
            formData.append("file", file);
            formData.append("provider_name", provName);
            formData.append("tariff_name", tName);

            btnUploadTariff.disabled = true;
            btnUploadTariff.textContent = "⏳ Procesando...";

            try {
                const res = await fetch("/api/tariffs/upload", {
                    method: "POST",
                    body: formData
                });
                const data = await res.json();
                if (res.ok) {
                    alert(`✅ Tarifa de '${data.tariff.provider_name}' procesada con éxito!\nReferencias extraídas: ${data.tariff.total_items}\nFormato: ${data.tariff.file_type.toUpperCase()}`);
                    tariffFileInput.value = "";
                    if (tariffNameInput) tariffNameInput.value = "";
                    await loadSavedTariffs(data.tariff.id);
                } else {
                    alert(`❌ Error al procesar tarifa: ${data.detail || 'Formato no reconocido'}`);
                }
            } catch (err) {
                alert(`❌ Error de conexión al subir tarifa: ${err.message}`);
            } finally {
                btnUploadTariff.disabled = false;
                btnUploadTariff.textContent = "⬆ Guardar Tarifa";
            }
        });
    }

    async function loadAuditSnapshots() {
        if (!selectAuditSnapshot) return;
        try {
            const res = await fetch("/api/stock/history");
            const snapshots = await res.json();
            
            selectAuditSnapshot.innerHTML = "";
            if (selectDeltaOld) selectDeltaOld.innerHTML = "";
            if (selectDeltaNew) selectDeltaNew.innerHTML = "";

            if (!snapshots || snapshots.length === 0) {
                selectAuditSnapshot.innerHTML = '<option value="">Inventario actual (inventory.json)</option>';
                if (selectDeltaOld) selectDeltaOld.innerHTML = '<option value="">Sin histórico</option>';
                if (selectDeltaNew) selectDeltaNew.innerHTML = '<option value="">Sin histórico</option>';
                if (snapshotMetaInfo) snapshotMetaInfo.innerHTML = "<em>No hay snapshots en historial. Se usará el inventario actual.</em>";
                return;
            }

            selectAuditSnapshot.innerHTML = '<option value="">-- Inventario Actual en Sistema --</option>';
            snapshots.forEach((snap, idx) => {
                const opt = document.createElement("option");
                opt.value = snap.id;
                opt.textContent = `📅 ${snap.date} (${snap.total_references} refs, ${snap.total_units} uds) - ${snap.filename || 'PDF'}`;
                selectAuditSnapshot.appendChild(opt);

                if (selectDeltaOld) {
                    const optOld = document.createElement("option");
                    optOld.value = snap.id;
                    optOld.textContent = `${snap.date} (${snap.filename || 'PDF'})`;
                    selectDeltaOld.appendChild(optOld);
                }

                if (selectDeltaNew) {
                    const optNew = document.createElement("option");
                    optNew.value = snap.id;
                    optNew.textContent = `${snap.date} (${snap.filename || 'PDF'})`;
                    selectDeltaNew.appendChild(optNew);
                }
            });

            // Por defecto en el comparador delta, poner T1 = anterior y T2 = más reciente
            if (snapshots.length >= 2 && selectDeltaOld && selectDeltaNew) {
                selectDeltaNew.selectedIndex = 0;
                selectDeltaOld.selectedIndex = 1;
            }

            updateSnapshotMetaInfo();
        } catch (err) {
            console.error("Error cargando snapshots de stock:", err);
        }
    }

    function updateSnapshotMetaInfo() {
        if (!snapshotMetaInfo || !selectAuditSnapshot) return;
        const selText = selectAuditSnapshot.options[selectAuditSnapshot.selectedIndex]?.text || '';
        snapshotMetaInfo.innerHTML = `<span style="color: #10b981;">●</span> Inventario seleccionado: <strong>${selText}</strong>`;
    }

    if (selectAuditSnapshot) {
        selectAuditSnapshot.addEventListener("change", () => {
            updateSnapshotMetaInfo();
            loadAuditBrands();
        });
    }

    async function loadAuditBrands() {
        if (!selectAuditBrand) return;
        try {
            const snapId = selectAuditSnapshot?.value || '';
            const res = await fetch(`/api/stock/brands?snapshot_id=${encodeURIComponent(snapId)}`);
            const brands = await res.json();
            selectAuditBrand.innerHTML = '<option value="Todas">Todas las Marcas</option>';
            brands.forEach(b => {
                const opt = document.createElement("option");
                opt.value = b;
                opt.textContent = b;
                selectAuditBrand.appendChild(opt);
            });
        } catch (err) {
            console.error("Error cargando marcas de stock:", err);
        }
    }

    // Subida de PDF para auditoría con detección de fecha
    if (btnUploadAuditPdf && auditFileInput) {
        btnUploadAuditPdf.addEventListener("click", async () => {
            if (!auditFileInput.files || auditFileInput.files.length === 0) {
                alert("Por favor selecciona un archivo PDF de stock exportado de tu ERP.");
                return;
            }

            const file = auditFileInput.files[0];
            const formData = new FormData();
            formData.append("file", file);
            if (auditManualDate && auditManualDate.value) {
                formData.append("manual_date", auditManualDate.value);
            }

            btnUploadAuditPdf.disabled = true;
            btnUploadAuditPdf.textContent = "⏳ Analizando PDF...";

            try {
                const res = await fetch("/api/stock/upload-audit-pdf", {
                    method: "POST",
                    body: formData
                });
                const data = await res.json();
                if (res.ok) {
                    alert(`✅ Inventario procesado con éxito!\nFecha detectada: ${data.detected_date}\nReferencias: ${data.total_references}\nUnidades totales: ${data.total_units}`);
                    auditFileInput.value = "";
                    await loadAuditSnapshots();
                    await loadAuditBrands();
                } else {
                    alert(`❌ Error al procesar PDF: ${data.detail || 'Formato no reconocido'}`);
                }
            } catch (err) {
                alert(`❌ Error de conexión al subir PDF: ${err.message}`);
            } finally {
                btnUploadAuditPdf.disabled = false;
                btnUploadAuditPdf.textContent = "⬆ Subir PDF ERP";
            }
        });
    }

    // Ejecutar auditoría de faltas y cruce de stock vs catálogo
    if (btnRunAudit) {
        btnRunAudit.addEventListener("click", async () => {
            const providerId = selectAuditProvider?.value;
            if (!providerId) {
                alert("Por favor selecciona una tarifa de proveedor activa para auditar.");
                selectAuditProvider?.focus();
                return;
            }

            const brand = selectAuditBrand?.value || "Todas";
            const snapId = selectAuditSnapshot?.value || "";
            const threshold = parseInt(inputAuditThreshold?.value || "2", 10);

            btnRunAudit.disabled = true;
            btnRunAudit.textContent = "⏳ Comprobando existencias...";

            try {
                const res = await fetch("/api/stock/audit-shortages", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        provider_id: providerId,
                        brand: brand,
                        snapshot_id: snapId,
                        threshold: threshold
                    })
                });

                const data = await res.json();
                if (res.ok) {
                    auditShortagesData = data;
                    renderAuditResults(data);
                } else {
                    alert(`❌ Error al comprobar faltas: ${data.detail || 'Ocurrió un error'}`);
                }
            } catch (err) {
                alert(`❌ Error al conectar con el servidor: ${err.message}`);
            } finally {
                btnRunAudit.disabled = false;
                btnRunAudit.textContent = "🔍 Comprobar Faltas";
            }
        });
    }

    function renderAuditResults(data) {
        const kpis = data.kpis || {};
        
        // Actualizar KPIs
        const elShortages = document.getElementById("audit-kpi-shortages");
        const elLow = document.getElementById("audit-kpi-low");
        const elOk = document.getElementById("audit-kpi-ok");
        const elCost = document.getElementById("audit-kpi-cost");

        if (elShortages) elShortages.textContent = kpis.shortages_count || 0;
        if (elLow) elLow.textContent = kpis.low_stock_count || 0;
        if (elOk) elOk.textContent = kpis.in_stock_count || 0;
        if (elCost) elCost.textContent = `${(kpis.total_estimated_reorder_cost || 0).toLocaleString('es-ES', { minimumFractionDigits: 2 })} €`;

        // Actualizar badges en subtabs
        const bShortages = document.getElementById("count-badge-shortages");
        const bLow = document.getElementById("count-badge-low");
        const bOk = document.getElementById("count-badge-ok");
        const bSurplus = document.getElementById("count-badge-surplus");

        if (bShortages) bShortages.textContent = kpis.shortages_count || 0;
        if (bLow) bLow.textContent = kpis.low_stock_count || 0;
        if (bOk) bOk.textContent = kpis.in_stock_count || 0;
        if (bSurplus) bSurplus.textContent = kpis.surplus_count || 0;

        // Renderizar tabla de Faltas (Roturas)
        const tbodyShortages = document.getElementById("table-body-shortages");
        if (tbodyShortages) {
            tbodyShortages.innerHTML = "";
            if (!data.shortages || data.shortages.length === 0) {
                tbodyShortages.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #10b981; padding: 25px;">🎉 ¡Excelente! No tienes ninguna falta para esta marca y tarifa.</td></tr>';
            } else {
                data.shortages.forEach(it => {
                    const tr = document.createElement("tr");
                    tr.style.background = "rgba(239, 68, 68, 0.05)";
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(it.model)}</strong></td>
                        <td style="max-width: 320px; font-size: 12px;">${escapeHtml(it.product)}</td>
                        <td><span class="badge" style="font-size: 11px;">${escapeHtml(it.category)}</span></td>
                        <td style="text-align: center;"><span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #ef4444; font-weight: 700;">0 uds</span></td>
                        <td style="text-align: center;"><strong style="color: #3b82f6;">+${it.suggested_reorder} uds</strong></td>
                        <td style="text-align: right;">${it.supplier_price.toLocaleString('es-ES', { minimumFractionDigits: 2 })} €</td>
                        <td style="text-align: right; font-weight: 700; color: #ef4444;">${it.reorder_cost.toLocaleString('es-ES', { minimumFractionDigits: 2 })} €</td>
                    `;
                    tbodyShortages.appendChild(tr);
                });
            }
        }

        // Renderizar tabla de Stock Bajo
        const tbodyLow = document.getElementById("table-body-low");
        if (tbodyLow) {
            tbodyLow.innerHTML = "";
            if (!data.low_stock || data.low_stock.length === 0) {
                tbodyLow.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 20px;">No hay productos en estado de stock bajo.</td></tr>';
            } else {
                data.low_stock.forEach(it => {
                    const tr = document.createElement("tr");
                    tr.style.background = "rgba(245, 158, 11, 0.05)";
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(it.model)}</strong></td>
                        <td style="max-width: 320px; font-size: 12px;">${escapeHtml(it.product)}</td>
                        <td><span class="badge" style="font-size: 11px;">${escapeHtml(it.category)}</span></td>
                        <td style="text-align: center;"><span class="badge" style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; font-weight: 700;">${it.stock} uds</span></td>
                        <td style="text-align: center;"><strong style="color: #3b82f6;">+${it.suggested_reorder} uds</strong></td>
                        <td style="text-align: right;">${it.supplier_price.toLocaleString('es-ES', { minimumFractionDigits: 2 })} €</td>
                        <td style="text-align: right; font-weight: 700;">${it.reorder_cost.toLocaleString('es-ES', { minimumFractionDigits: 2 })} €</td>
                    `;
                    tbodyLow.appendChild(tr);
                });
            }
        }

        // Renderizar tabla de En Stock
        const tbodyOk = document.getElementById("table-body-ok");
        if (tbodyOk) {
            tbodyOk.innerHTML = "";
            if (!data.in_stock || data.in_stock.length === 0) {
                tbodyOk.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 20px;">Sin referencias en esta categoría.</td></tr>';
            } else {
                data.in_stock.forEach(it => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(it.model)}</strong></td>
                        <td style="max-width: 380px; font-size: 12px;">${escapeHtml(it.product)}</td>
                        <td><span class="badge" style="font-size: 11px;">${escapeHtml(it.category)}</span></td>
                        <td style="text-align: center;"><span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #10b981; font-weight: 700;">${it.stock} uds</span></td>
                        <td style="text-align: right;">${it.supplier_price.toLocaleString('es-ES', { minimumFractionDigits: 2 })} €</td>
                    `;
                    tbodyOk.appendChild(tr);
                });
            }
        }

        // Renderizar tabla de Excedentes / No en Tarifa
        const tbodySurplus = document.getElementById("table-body-surplus");
        if (tbodySurplus) {
            tbodySurplus.innerHTML = "";
            if (!data.surplus || data.surplus.length === 0) {
                tbodySurplus.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 20px;">Todo el stock de almacén coincide con la tarifa.</td></tr>';
            } else {
                data.surplus.forEach(it => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(it.sku)}</strong></td>
                        <td style="max-width: 380px; font-size: 12px;">${escapeHtml(it.description)}</td>
                        <td><span class="badge" style="font-size: 11px;">${escapeHtml(it.category)}</span></td>
                        <td style="text-align: center;">${it.stock} uds</td>
                        <td style="text-align: right;">${(it.cost || 0).toLocaleString('es-ES', { minimumFractionDigits: 2 })} €</td>
                    `;
                    tbodySurplus.appendChild(tr);
                });
            }
        }
    }

    // Calcular Ventas y Delta entre 2 Snapshots
    if (btnRunSalesDelta) {
        btnRunSalesDelta.addEventListener("click", async () => {
            const oldId = selectDeltaOld?.value;
            const newId = selectDeltaNew?.value;

            if (!oldId || !newId) {
                alert("Selecciona dos snapshots para comparar.");
                return;
            }
            if (oldId === newId) {
                alert("Debes seleccionar dos snapshots con fechas distintas para calcular ventas.");
                return;
            }

            const brand = selectAuditBrand?.value || "Todas";

            btnRunSalesDelta.disabled = true;
            btnRunSalesDelta.textContent = "⏳ Calculando...";

            try {
                const res = await fetch("/api/stock/analyze-sales", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        snapshot_old_id: oldId,
                        snapshot_new_id: newId,
                        brand: brand
                    })
                });

                const data = await res.json();
                if (res.ok) {
                    auditDeltaData = data;
                    renderSalesDeltaResults(data);
                    
                    // Activar visualmente la pestaña de ventas
                    const salesSubtabBtn = document.querySelector('[data-subtab="audit-subtab-sales"]');
                    if (salesSubtabBtn) salesSubtabBtn.click();
                } else {
                    alert(`❌ Error al calcular ventas: ${data.detail || 'Error'}`);
                }
            } catch (err) {
                alert(`❌ Error de conexión: ${err.message}`);
            } finally {
                btnRunSalesDelta.disabled = false;
                btnRunSalesDelta.textContent = "🔄 Calcular Ventas";
            }
        });
    }

    function renderSalesDeltaResults(data) {
        const kpis = data.kpis || {};
        const period = data.period || {};

        // Actualizar KPI Card de ventas
        const elSales = document.getElementById("audit-kpi-sales");
        const elSalesSub = document.getElementById("audit-kpi-sales-sub");
        const bSales = document.getElementById("count-badge-sales");

        if (elSales) elSales.textContent = `${kpis.total_units_sold || 0} uds`;
        if (elSalesSub) elSalesSub.textContent = `En ${period.days_elapsed || 1} días (${kpis.average_sales_per_day || 0} uds/día)`;
        if (bSales) bSales.textContent = kpis.products_with_sales || 0;

        // Renderizar tabla de ventas
        const tbody = document.getElementById("table-body-sales");
        if (!tbody) return;
        tbody.innerHTML = "";

        const allSold = data.all_sold || [];
        if (allSold.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 25px;">No se registraron ventas netas en el periodo (${period.date_old} a ${period.date_new}).</td></tr>`;
            return;
        }

        allSold.forEach(it => {
            const tr = document.createElement("tr");
            const isCritical = it.is_critical_burn;
            if (isCritical) {
                tr.style.background = "rgba(239, 68, 68, 0.08)";
            }
            tr.innerHTML = `
                <td><strong>${escapeHtml(it.sku)}</strong></td>
                <td><span class="badge" style="font-size: 11px;">${escapeHtml(it.brand)}</span></td>
                <td style="max-width: 300px; font-size: 12px;">${escapeHtml(it.description)}</td>
                <td style="text-align: center;">${it.stock_old}</td>
                <td style="text-align: center;"><strong>${it.stock_new}</strong></td>
                <td style="text-align: center;"><span class="badge" style="background: rgba(37, 99, 235, 0.15); color: #3b82f6; font-weight: 800;">${it.units_sold} uds</span></td>
                <td style="text-align: right; font-weight: 600;">${it.sales_rate_per_day} / día</td>
                <td style="text-align: center;">
                    ${it.stock_new === 0 
                        ? '<span class="badge" style="background: #ef4444; color: #fff;">AGOTADO (0d)</span>' 
                        : (isCritical 
                            ? `<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #ef4444; font-weight: 700;">⚠️ ${it.days_to_stockout} días</span>` 
                            : `${it.days_to_stockout} días`)}
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Generar informe cognitivo con Gemini
    if (btnTriggerGemini) {
        btnTriggerGemini.addEventListener("click", async () => {
            const providerId = selectAuditProvider?.value;
            if (!providerId) {
                alert("Por favor selecciona una tarifa de proveedor antes de generar el informe.");
                return;
            }

            const brand = selectAuditBrand?.value || "Todas";
            const threshold = parseInt(inputAuditThreshold?.value || "2", 10);
            const snapOldId = selectDeltaOld?.value || null;
            const snapNewId = selectDeltaNew?.value || selectAuditSnapshot?.value || null;

            if (cardGeminiExec) cardGeminiExec.style.display = "block";
            if (geminiReportContent) {
                geminiReportContent.innerHTML = `
                    <div style="padding: 20px; text-align: center; color: #c4b5fd;">
                        <span class="spinner" style="display: inline-block; width: 24px; height: 24px; border: 3px solid rgba(196, 181, 253, 0.3); border-top-color: #c4b5fd; border-radius: 50%; animation: spin 1s linear infinite;"></span>
                        <p style="margin-top: 10px; font-weight: 600;">Gemini está analizando las existencias, ventas y calculando la propuesta óptima de compra...</p>
                    </div>
                `;
            }

            btnTriggerGemini.disabled = true;

            try {
                const res = await fetch("/api/stock/gemini-report", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        provider_id: providerId,
                        brand: brand,
                        snapshot_old_id: snapOldId,
                        snapshot_new_id: snapNewId,
                        threshold: threshold
                    })
                });

                const data = await res.json();
                if (res.ok) {
                    if (geminiReportContent) {
                        geminiReportContent.innerHTML = formatMarkdownToHtml(data.report || "Sin contenido.");
                    }
                } else {
                    if (geminiReportContent) {
                        geminiReportContent.innerHTML = `<div style="color: #ef4444; padding: 10px;">❌ Error: ${data.detail || 'No se pudo generar el informe.'}</div>`;
                    }
                }
            } catch (err) {
                if (geminiReportContent) {
                    geminiReportContent.innerHTML = `<div style="color: #ef4444; padding: 10px;">❌ Error de conexión: ${err.message}</div>`;
                }
            } finally {
                btnTriggerGemini.disabled = false;
            }
        });
    }

    // Exportar a Excel
    if (btnExportAuditXlsx) {
        btnExportAuditXlsx.addEventListener("click", () => {
            const providerId = selectAuditProvider?.value;
            if (!providerId) {
                alert("Selecciona una tarifa de proveedor para exportar el pedido.");
                return;
            }
            const brand = selectAuditBrand?.value || "Todas";
            const threshold = inputAuditThreshold?.value || "2";
            const snapNew = selectDeltaNew?.value || selectAuditSnapshot?.value || '';
            const snapOld = selectDeltaOld?.value || '';

            const url = `/api/stock/audit/export/xlsx?provider_id=${encodeURIComponent(providerId)}&brand=${encodeURIComponent(brand)}&threshold=${encodeURIComponent(threshold)}&snapshot_new_id=${encodeURIComponent(snapNew)}&snapshot_old_id=${encodeURIComponent(snapOld)}`;
            window.location.href = url;
        });
    }

    function formatMarkdownToHtml(md) {
        if (!md) return '';
        let html = md
            .replace(/^### (.*$)/gim, '<h4 style="color: #93c5fd; margin: 12px 0 6px 0; font-size: 15px;">$1</h4>')
            .replace(/^## (.*$)/gim, '<h3 style="color: #c4b5fd; margin: 16px 0 8px 0; font-size: 16px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px;">$1</h3>')
            .replace(/^# (.*$)/gim, '<h2 style="color: #e0e7ff; margin: 18px 0 10px 0; font-size: 18px;">$1</h2>')
            .replace(/\*\*(.*?)\*\*/gim, '<strong style="color: #f8fafc;">$1</strong>')
            .replace(/\*(.*?)\*/gim, '<em>$1</em>')
            .replace(/^- (.*$)/gim, '<li style="margin-left: 20px; list-style-type: disc;">$1</li>')
            .replace(/\n/gim, '<br>');
        return html;
    }

    // Initialize Page
    initSSEConnection();
    loadStatus();
    loadGeminiConfig();
    initAuditTab();
});

