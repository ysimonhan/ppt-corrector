const BASE_URL = "https://YOUR-RAILWAY-APP.up.railway.app";

const file = data.input.document;
if (!file || !file.base64 || !file.fileName) {
  throw new Error("Missing required input: document");
}

const highlight = Boolean(data.input.highlight);

const response = await ld.request({
  method: "POST",
  url: `${BASE_URL}/jobs?highlight=${highlight ? "true" : "false"}`,
  headers: {
    Authorization: `Bearer ${data.auth.apiKey}`,
    "Content-Type": "application/json",
  },
  body: {
    file_base64: file.base64,
    file_name: file.fileName,
  },
});

if (response.status !== 202) {
  const errorBody = response.json || response.text || "No body returned";
  throw new Error(
    `Job creation failed with status ${response.status}: ${JSON.stringify(errorBody)}`
  );
}

const result = response.json;

return {
  job_id: result.job_id,
  status: "processing",
  message:
    `Correction started. Job ID: ${result.job_id}. ` +
    "Use the Get Correction Result action with this job ID to retrieve the corrected PowerPoint.",
};
