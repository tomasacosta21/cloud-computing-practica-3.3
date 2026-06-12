const form = document.querySelector("#upload-form");
const result = document.querySelector("#result");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  result.textContent = "Preparando subida...";

  const apiBaseUrl = form.elements["api-url"].value.replace(/\/$/, "");
  const file = form.elements["invoice-file"].files[0];

  try {
    const uploadResponse = await fetch(`${apiBaseUrl}/batches/upload-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fileName: file.name }),
    });

    const uploadData = await uploadResponse.json();
    if (!uploadResponse.ok) {
      throw new Error(uploadData.error || "No se pudo generar la URL de subida");
    }

    const s3Response = await fetch(uploadData.uploadUrl, {
      method: "PUT",
      body: file,
    });

    if (!s3Response.ok) {
      throw new Error("S3 rechazo la subida del archivo");
    }

    result.textContent = JSON.stringify(
      {
        message: "Archivo subido",
        batchId: uploadData.batchId,
        s3Key: uploadData.s3Key,
      },
      null,
      2
    );
  } catch (error) {
    result.textContent = JSON.stringify({ error: error.message }, null, 2);
  }
});
