/**
 * SS12000 API Validator - Frontend JavaScript
 */

// Global state
let headerCount = 0;
let selectedCertificateFile = null;

/**
 * Initialize the form on page load
 */
document.addEventListener("DOMContentLoaded", function () {
    loadScenarios();
    setupEventListeners();
    addInitialHeader();
    setupDragAndDrop();
});

/**
 * Switch between tabs
 */
function switchTab(tabName, buttonElement) {
    // Hide all tabs
    document.querySelectorAll(".tab-content").forEach((tab) => {
        tab.classList.remove("active");
    });

    // Remove active class from all buttons
    document.querySelectorAll(".tab-button").forEach((btn) => {
        btn.classList.remove("active");
    });

    // Show selected tab
    document.getElementById(tabName).classList.add("active");
    buttonElement.classList.add("active");
}

/**
 * Setup drag and drop for certificate file
 */
function setupDragAndDrop() {
    const fileWrapper = document.getElementById("fileInputWrapper");

    fileWrapper.addEventListener("dragover", function (e) {
        e.preventDefault();
        fileWrapper.style.borderColor = "#6b8e23";
        fileWrapper.style.background = "#f1faf0";
    });

    fileWrapper.addEventListener("dragleave", function (e) {
        e.preventDefault();
        fileWrapper.style.borderColor = "#ddd";
        fileWrapper.style.background = "#fafafa";
    });

    fileWrapper.addEventListener("drop", function (e) {
        e.preventDefault();
        fileWrapper.style.borderColor = "#ddd";
        fileWrapper.style.background = "#fafafa";

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            document.getElementById("certificateFile").files = files;
            handleCertificateFileSelect({ target: { files: files } });
        }
    });
}

/**
 * Handle certificate file selection
 */
function handleCertificateFileSelect(event) {
    const file = event.target.files[0];

    if (!file) {
        return;
    }

    if (!file.name.endsWith(".json")) {
        showAlert("error", "Välj en JSON-certifikatfil");
        return;
    }

    selectedCertificateFile = file;

    // Update UI
    const fileWrapper = document.getElementById("fileInputWrapper");
    fileWrapper.innerHTML = `<p style="color: #6b8e23; margin: 0;"><strong>✓ ${file.name}</strong></p><p style="color: #999; font-size: 12px;">Redo att verifiera</p>`;

    document.getElementById("verifyBtn").style.display = "inline-block";
    document.getElementById("clearCertBtn").style.display = "inline-block";
}

/**
 * Clear certificate file selection
 */
function clearCertificateFile() {
    selectedCertificateFile = null;
    document.getElementById("certificateFile").value = "";

    const fileWrapper = document.getElementById("fileInputWrapper");
    fileWrapper.innerHTML = `<p class="drag-text">📄 Klicka för att välja eller dra och släpp</p><p>Certifikatfil</p>`;

    document.getElementById("verifyBtn").style.display = "none";
    document.getElementById("clearCertBtn").style.display = "none";
    document.getElementById("verificationResult").classList.remove("show");
}

/**
 * Load scenarios from the API and populate the dropdown
 */
async function loadScenarios() {
    try {
        const response = await fetch("/api/scenarios");
        const data = await response.json();

        const scenariosSelect = document.getElementById("scenarios");
        scenariosSelect.innerHTML = ""; // Clear existing options

        if (data.scenarios && data.scenarios.length > 0) {
            data.scenarios.forEach((scenario) => {
                const option = document.createElement("option");
                option.value = scenario.id;
                option.textContent = `${scenario.name}`;
                scenariosSelect.appendChild(option);
            });
        } else {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "Inga scenarier tillgängliga. Kontrollera konfigurationen i scenarios.yaml.";
            option.disabled = true;
            scenariosSelect.appendChild(option);
        }
    } catch (error) {
        console.error("Error loading scenarios:", error);
        const scenariosSelect = document.getElementById("scenarios");
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "Fel vid inläsning av scenarier";
        option.disabled = true;
        scenariosSelect.appendChild(option);
    }
}

/**
 * Setup event listeners for form interactions
 */
function setupEventListeners() {
    // Form submission
    document.getElementById("validationForm").addEventListener("submit", handleFormSubmit);

    // Add header button
    document.getElementById("addHeaderBtn").addEventListener("click", addHeaderRow);

    // Enable/disable limit input
    document.getElementById("enableLimit").addEventListener("change", function () {
        const limitGroup = document.getElementById("limitGroup");
        limitGroup.style.display = this.checked ? "flex" : "none";
    });

    // Reset form
    document.getElementById("validationForm").addEventListener("reset", function () {
        document.getElementById("limitGroup").style.display = "none";
        document.getElementById("results").classList.remove("show");
        addInitialHeader();
    });
}

/**
 * Add the initial empty header row
 */
function addInitialHeader() {
    const container = document.getElementById("headersContainer");
    container.innerHTML = ""; // Clear all headers
    headerCount = 0;
    addHeaderRow();
}

/**
 * Add a new header row to the form
 */
function addHeaderRow(event) {
    if (event) {
        event.preventDefault();
    }

    const container = document.getElementById("headersContainer");
    const headerId = headerCount++;

    const headerRow = document.createElement("div");
    headerRow.className = "header-row";
    headerRow.id = `header-${headerId}`;

    const keyInput = document.createElement("input");
    keyInput.type = "text";
    keyInput.name = `header-key-${headerId}`;
    keyInput.placeholder = "Header (ex, Authorization)";

    const valueInput = document.createElement("input");
    valueInput.type = "text";
    valueInput.name = `header-value-${headerId}`;
    valueInput.placeholder = "Header value (ex, Bearer token)";

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-remove-header";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", function (e) {
        e.preventDefault();
        headerRow.remove();
    });

    headerRow.appendChild(keyInput);
    headerRow.appendChild(valueInput);
    headerRow.appendChild(removeBtn);
    container.appendChild(headerRow);
}

/**
 * Handle form submission
 */
async function handleFormSubmit(event) {
    event.preventDefault();

    // Validate form
    const apiUrl = document.getElementById("apiUrl").value.trim();
    const version = document.getElementById("version").value;
    const scenariosSelect = document.getElementById("scenarios");
    const selectedScenarios = Array.from(scenariosSelect.selectedOptions).map((opt) => opt.value);

    if (!apiUrl) {
        showAlert("error", "API-URL är obligatorisk");
        return;
    }

    if (selectedScenarios.length === 0) {
    showAlert("error", "Välj minst ett scenario");
        return;
    }

    // Collect headers
    const headers = [];
    document.querySelectorAll(".header-row").forEach((row) => {
        const keyInput = row.querySelector('input[name*="header-key"]');
        const valueInput = row.querySelector('input[name*="header-value"]');

        if (keyInput && valueInput && keyInput.value.trim() && valueInput.value.trim()) {
            headers.push({
                key: keyInput.value.trim(),
                value: valueInput.value.trim(),
            });
        }
    });

    // Get limit if enabled
    let limit = 10;
    if (document.getElementById("enableLimit").checked) {
        limit = parseInt(document.getElementById("limitValue").value) || 10;
        if (limit < 1 || limit > 50) {
            showAlert("error", "Gräns måste vara mellan 1 och 50");
            return;
        }
    }

    // Prepare request payload
    const payload = {
        api_url: apiUrl,
        version: version,
        scenarios: selectedScenarios,
        headers: headers,
        limit: limit,
    };

    // Show loading state
    document.getElementById("loading").style.display = "block";
    document.getElementById("submitBtn").disabled = true;

    try {
        const response = await fetch("/api/validate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json();

        document.getElementById("loading").style.display = "none";
        document.getElementById("submitBtn").disabled = false;

        if (!response.ok) {
        showAlert("error", data.detail || "Validering misslyckades");
            return;
        }

        // Display results
        displayResults(data);
    } catch (error) {
        console.error("Error during validation:", error);
        showAlert("error", `Error: ${error.message}`);
        document.getElementById("loading").style.display = "none";
        document.getElementById("submitBtn").disabled = false;
    }
}

/**
 * Display validation results
 */
function displayResults(data) {
    const resultsDiv = document.getElementById("results");
    const contentDiv = document.getElementById("resultsContent");
    const status = data.status;

    let html = `<div class="result-header">
        <span class="result-status ${status}">${status.toUpperCase()}</span>
    </div>`;

    if (data.test_results) {
        const testResults = data.test_results;

        html += `<div style="margin-bottom: 20px; font-size: 14px; color: #666;">
            <strong>Sammanfattning:</strong> ${testResults.passed_scenarios} av ${testResults.total_scenarios} scenarier passerade
        </div>`;

        // Display each scenario result
        if (testResults.scenarios) {
            Object.entries(testResults.scenarios).forEach(([scenarioId, scenarioResult]) => {
                const scenarioStatus = scenarioResult.status;
                html += `
                    <div class="scenario-result ${scenarioStatus}">
                        <div class="scenario-name">
                            ${scenarioResult.scenario_name}
                            <span style="color: #999; font-weight: normal; font-size: 12px;">
                                [${scenarioStatus.toUpperCase()}]
                            </span>
                        </div>
                `;

                // Display steps
                if (scenarioResult.steps && scenarioResult.steps.length > 0) {
                    scenarioResult.steps.forEach((step) => {
                        html += `<div class="step-result ${step.status}">
                            <strong>${step.name}</strong> [${step.method} ${step.endpoint}]`;

                        if (step.status === "fail" && step.error_details) {
                            html += `
                                <div class="error-details">
                                    ${escapeHtml(step.error_details)}
                                </div>
                            `;
                        }

                        html += `</div>`;
                    });
                }

                if (scenarioResult.error_summary) {
                    html += `<div class="error-details">${escapeHtml(scenarioResult.error_summary)}</div>`;
                }

                html += `</div>`;
            });
        }

        // Add certificate download button if all passed
        if (data.certificate) {
            html += `
                <button type="button" class="btn btn-primary btn-download-cert" onclick="downloadCertificate(${JSON.stringify(data.certificate).replace(/"/g, '&quot;')})">
                    Ladda ned efterlevnadscertifikat
                </button>
            `;
        } else if (status === "fail") {
            html += `
                <div style="margin-top: 15px; padding: 12px; background: #ffe3e3; border-radius: 4px; color: #c92a2a; font-size: 12px;">
                    Certifikatet är inte tillgängligt eftersom vissa valideringsscenarier misslyckades. Fixa problemen och försök igen.
                </div>
            `;
        }
    }

    contentDiv.innerHTML = html;
    resultsDiv.classList.add("show");
    resultsDiv.classList.toggle("success", status === "pass");
    resultsDiv.classList.toggle("error", status === "fail");

    // Scroll to results
    resultsDiv.scrollIntoView({ behavior: "smooth", block: "start" });
}

/**
 * Download certificate as JSON file
 */
function downloadCertificate(certificate) {
    const dataStr = JSON.stringify(certificate, null, 2);
    const dataBlob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `ss12000-efterlevnadscertifikat-${new Date().toISOString().split("T")[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

/**
 * Verify uploaded certificate
 */
async function verifyCertificate() {
    if (!selectedCertificateFile) {
        showAlert("error", "Välj en certifikatfil");
        return;
    }

    const formData = new FormData();
    formData.append("file", selectedCertificateFile);

    try {
        const response = await fetch("/api/verify-certificate", {
            method: "POST",
            body: formData,
        });

        const data = await response.json();

        if (!response.ok) {
            showAlert("error", data.detail || "Verifiering misslyckades");
            return;
        }

        displayVerificationResult(data);
    } catch (error) {
        console.error("Error verifying certificate:", error);
        showAlert("error", `Error: ${error.message}`);
    }
}

/**
 * Display certificate verification result
 */
function displayVerificationResult(result) {
    const resultDiv = document.getElementById("verificationResult");

    let html = `<h3>${result.valid ? "✓ Certifikat giltigt" : "✗ Certifikat ogiltigt"}</h3>`;

    if (result.message) {
        html += `<p style="color: #666; font-size: 13px; margin-bottom: 15px;">${escapeHtml(result.message)}</p>`;
    }

    html += `<div class="verification-details">`;

    if (result.api_url) {
        html += `<div><strong>API-URL:</strong> <span style="word-break: break-all;">${escapeHtml(result.api_url)}</span></div>`;
    }

    if (result.ss12000_version) {
        html += `<div><strong>Version:</strong> ${result.ss12000_version}</div>`;
    }

    if (result.overall_status) {
        html += `<div><strong>Overallstatus:</strong> ${result.overall_status}</div>`;
    }

    if (result.issued_at) {
        html += `<div><strong>Utfärdad:</strong> ${new Date(result.issued_at).toLocaleString()}</div>`;
    }

    if (result.expires_at) {
        html += `<div><strong>Upphör:</strong> ${new Date(result.expires_at).toLocaleString()}</div>`;
    }

    if (result.scenarios_tested && result.scenarios_tested.length > 0) {
        html += `<div><strong>Scenarier:</strong> ${result.scenarios_tested.join(", ")}</div>`;
    }

    html += `</div>`;

    resultDiv.innerHTML = html;
    resultDiv.classList.add("show");
    resultDiv.classList.toggle("valid", result.valid);
    resultDiv.classList.toggle("invalid", !result.valid);
}

/**
 * Show alert message
 */
function showAlert(type, message) {
    // Remove existing alerts
    const existingAlerts = document.querySelectorAll(".alert");
    existingAlerts.forEach((alert) => alert.remove());

    const form = document.getElementById("validationForm");
    const alert = document.createElement("div");
    alert.className = `alert alert-${type}`;
    alert.textContent = message;

    form.insertBefore(alert, form.firstChild);

    // Auto-remove alert after 10 seconds
    setTimeout(() => alert.remove(), 10000);
}

/**
 * Escape HTML special characters to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return "";
    const map = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
    };
    return text.replace(/[&<>"']/g, (m) => map[m]);
}
