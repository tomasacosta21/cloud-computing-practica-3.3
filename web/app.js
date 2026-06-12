const apiInput = document.querySelector("#api-url");
const settingsToggle = document.querySelector("#settings-toggle");
const settingsPanel = document.querySelector("#settings-panel");
const uploadForm = document.querySelector("#upload-form");
const queryForm = document.querySelector("#query-form");
const fileInput = document.querySelector("#invoice-file");
const batchInput = document.querySelector("#batch-id");
const uploadButton = document.querySelector("#upload-button");
const queryButton = document.querySelector("#query-button");
const pageSizeInput = document.querySelector("#page-size");
const pageIndicator = document.querySelector("#page-indicator");
const previousPageButton = document.querySelector("#previous-page-button");
const nextPageButton = document.querySelector("#next-page-button");
const uploadStatus = document.querySelector("#upload-status");
const batchSummary = document.querySelector("#batch-summary");
const invoicesBody = document.querySelector("#invoices-body");

const API_BASE_KEY = "facturasApiBaseUrl";
const configuredApiBaseUrl = window.APP_CONFIG?.apiBaseUrl || "";
let currentBatchId = "";
let currentPageToken = null;
let currentPageNumber = 1;
let nextPageToken = null;
let previousPageTokens = [];
let isQueryLoading = false;
let isPagerLoading = false;

apiInput.value = configuredApiBaseUrl || localStorage.getItem(API_BASE_KEY) || "http://127.0.0.1:3000";
apiInput.addEventListener("change", () => {
  localStorage.setItem(API_BASE_KEY, normalizedApiBaseUrl());
});

batchInput.addEventListener("input", () => {
  batchInput.setCustomValidity("");
});

settingsToggle.addEventListener("click", () => {
  const isOpen = !settingsPanel.hidden;
  settingsPanel.hidden = isOpen;
  settingsToggle.setAttribute("aria-expanded", String(!isOpen));
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];

  if (!file) {
    setUploadStatus({
      type: "error",
      title: "Falta seleccionar archivo",
      message: "Selecciona un archivo .xlsx para subir un lote.",
    });
    return;
  }

  setUploadLoading(true);
  setUploadStatus({
    type: "info",
    title: "Preparando subida",
    message: "Generando URL prefirmada y subiendo el archivo a S3.",
  });

  try {
    const uploadData = await createUploadUrl(file.name);
    await uploadToS3(uploadData, file);

    batchInput.value = uploadData.batchId;
    setUploadStatus({
      type: "success",
      title: "Archivo subido correctamente",
      batchId: uploadData.batchId,
      message: "El batchId ya se cargo en el campo de busqueda. Presiona Consultar para ver el avance.",
    });
    clearBatchResults();
  } catch (error) {
    setUploadStatus({
      type: "error",
      title: "No se pudo subir el lote",
      message: error.message,
    });
  } finally {
    setUploadLoading(false);
  }
});

queryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runQueryAction(() => loadCurrentBatch());
});

previousPageButton.addEventListener("click", async () => {
  if (!previousPageTokens.length) {
    return;
  }

  await runPagerAction(async () => {
    const previousToken = previousPageTokens[previousPageTokens.length - 1];
    await loadBatch(currentBatchId, {
      pageNumber: Math.max(1, currentPageNumber - 1),
      pageToken: previousToken,
    });
    previousPageTokens.pop();
    renderPager();
  });
});

nextPageButton.addEventListener("click", async () => {
  if (!nextPageToken) {
    return;
  }

  await runPagerAction(async () => {
    const tokenForCurrentPage = currentPageToken;
    await loadBatch(currentBatchId, {
      pageNumber: currentPageNumber + 1,
      pageToken: nextPageToken,
    });
    previousPageTokens.push(tokenForCurrentPage);
    renderPager();
  });
});

pageSizeInput.addEventListener("change", async () => {
  if (!currentBatchId) {
    return;
  }

  await runPagerAction(async () => {
    previousPageTokens = [];
    await loadBatch(currentBatchId, { pageNumber: 1, pageToken: null });
  });
});

async function createUploadUrl(fileName) {
  const response = await fetch(`${normalizedApiBaseUrl()}/batches/upload-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fileName }),
  });
  const body = await response.json();

  if (!response.ok) {
    throw new Error(body.error || "No se pudo generar la URL de subida");
  }

  return body;
}

async function uploadToS3(uploadData, file) {
  const response = await fetch(uploadData.uploadUrl, {
    method: uploadData.uploadMethod || "PUT",
    headers: uploadData.uploadHeaders || {},
    body: file,
  });

  if (!response.ok) {
    throw new Error("S3 rechazó la subida del archivo");
  }
}

async function loadCurrentBatch() {
  const batchId = batchInput.value.trim();
  if (!batchId) {
    throw new Error("Ingresa un batchId para consultar el lote.");
  }
  previousPageTokens = [];
  await loadBatch(batchId, { pageNumber: 1, pageToken: null });
}

async function loadBatch(batchId, options = {}) {
  const pageToken = options.pageToken ?? null;
  const pageNumber = options.pageNumber ?? currentPageNumber;
  currentBatchId = batchId;

  const [batch, invoices] = await Promise.all([getBatch(batchId), getInvoices(batchId, pageToken)]);
  currentPageToken = pageToken;
  currentPageNumber = pageNumber;
  nextPageToken = invoices.nextToken || null;

  renderBatch(batch);
  renderInvoices(invoices.items || []);
  renderPager();
}

async function runQueryAction(action) {
  setQueryLoading(true);
  batchInput.setCustomValidity("");

  try {
    await action();
  } catch (error) {
    batchInput.setCustomValidity(error.message);
    batchInput.reportValidity();
  } finally {
    setQueryLoading(false);
  }
}

async function runPagerAction(action) {
  setPagerLoading(true);

  try {
    await action();
  } catch (error) {
    console.error(error);
  } finally {
    setPagerLoading(false);
  }
}

async function getBatch(batchId) {
  const response = await fetch(`${normalizedApiBaseUrl()}/batches/${encodeURIComponent(batchId)}`);
  const body = await response.json();

  if (!response.ok) {
    throw new Error(body.error || "No se pudo consultar el lote");
  }

  return body;
}

async function getInvoices(batchId, pageToken) {
  const params = new URLSearchParams({
    limit: pageSizeInput.value,
  });
  if (pageToken) {
    params.set("nextToken", pageToken);
  }

  const response = await fetch(
    `${normalizedApiBaseUrl()}/batches/${encodeURIComponent(batchId)}/invoices?${params.toString()}`
  );
  const body = await response.json();

  if (!response.ok) {
    throw new Error(body.error || "No se pudieron consultar las facturas");
  }

  return body;
}

function renderBatch(batch) {
  const fields = [
    ["Estado", batch.status],
    ["Total", batch.totalInvoices],
    ["Procesadas", batch.processedInvoices],
    ["Validadas", batch.validatedInvoices],
    ["Rechazadas", batch.rejectedInvoices],
    ["Errores", batch.errorInvoices],
  ];

  batchSummary.innerHTML = fields
    .map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? 0)}</dd></div>`)
    .join("");
}

function renderInvoices(items) {
  if (!items.length) {
    invoicesBody.innerHTML = '<tr><td colspan="6" class="empty">Sin facturas para mostrar</td></tr>';
    return;
  }

  invoicesBody.innerHTML = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.invoiceNumber || "")}</td>
          <td><span class="badge">${escapeHtml(item.status || "")}</span></td>
          <td>${escapeHtml(item.customerName || "")}</td>
          <td>${escapeHtml(item.amount || "")}</td>
          <td>${escapeHtml(item.cae || "")}</td>
          <td>${escapeHtml((item.errorMessages || []).join(", "))}</td>
        </tr>
      `
    )
    .join("");
}

function clearBatchResults() {
  currentBatchId = "";
  currentPageToken = null;
  currentPageNumber = 1;
  nextPageToken = null;
  previousPageTokens = [];
  batchSummary.innerHTML = "";
  renderInvoices([]);
  renderPager();
}

function renderPager() {
  const isListLoading = isQueryLoading || isPagerLoading;
  pageSizeInput.disabled = isListLoading;
  pageIndicator.textContent = `Pagina ${currentPageNumber}`;
  previousPageButton.disabled = isListLoading || previousPageTokens.length === 0;
  nextPageButton.disabled = isListLoading || !nextPageToken;
}

function setUploadStatus(payload) {
  setNotice(uploadStatus, payload);
}

function setNotice(target, payload) {
  const type = payload.type || "info";
  const title = payload.title || "";
  const message = payload.message || "";
  const batchId = payload.batchId
    ? `<p class="notice-meta"><strong>Batch ID:</strong> <code>${escapeHtml(payload.batchId)}</code></p>`
    : "";

  target.className = `notice notice-${type}`;
  target.innerHTML = `
    ${title ? `<strong>${escapeHtml(title)}</strong>` : ""}
    ${message ? `<p>${escapeHtml(message)}</p>` : ""}
    ${batchId}
  `;
}

function setUploadLoading(isLoading) {
  uploadButton.disabled = isLoading;
  fileInput.disabled = isLoading;
  uploadButton.textContent = isLoading ? "Subiendo..." : "Subir lote";
}

function setQueryLoading(isLoading) {
  isQueryLoading = isLoading;
  queryButton.disabled = isLoading;
  queryButton.textContent = isLoading ? "Consultando..." : "Consultar";
  renderPager();
}

function setPagerLoading(isLoading) {
  isPagerLoading = isLoading;
  renderPager();
}

function normalizedApiBaseUrl() {
  const value = apiInput.value.trim().replace(/\/$/, "");
  if (value !== configuredApiBaseUrl) {
    localStorage.setItem(API_BASE_KEY, value);
  }
  return value;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
