import "./style.css";

const fileInput = document.querySelector("#file-input");
const dropZone = document.querySelector("#drop-zone");
const selectedFile = document.querySelector("#selected-file");
const uploadButton = document.querySelector("#upload-button");
const uploadMessage = document.querySelector("#upload-message");
const documentList = document.querySelector("#document-list");
const documentCount = document.querySelector("#document-count");
const chatForm = document.querySelector("#chat-form");
const questionInput = document.querySelector("#question-input");
const thinkingMode = document.querySelector("#thinking-mode");
const askButton = document.querySelector("#ask-button");
const chatHistory = document.querySelector("#chat-history");
const connectionStatus = document.querySelector("#connection-status");
const documentScope = document.querySelector("#document-scope");
const workspace = document.querySelector("#workspace");
const authPanel = document.querySelector("#auth-panel");
const authForm = document.querySelector("#auth-form");
const authTitle = document.querySelector("#auth-title");
const authSubmit = document.querySelector("#auth-submit");
const authToggle = document.querySelector("#auth-toggle");
const authMessage = document.querySelector("#auth-message");
const usernameInput = document.querySelector("#username-input");
const passwordInput = document.querySelector("#password-input");
const account = document.querySelector("#account");
const accountName = document.querySelector("#account-name");
const logoutButton = document.querySelector("#logout-button");
const welcomeTemplate = document.querySelector("#welcome").cloneNode(true);
const emptyListTemplate = document.querySelector(".empty-list").cloneNode(true);

let fileToUpload = null;
let indexedCount = 0;
let sessionDocuments = [];
let accessToken = null;
let activeUser = null;
let signupMode = false;

function setUploadMessage(message, isError = false) {
  uploadMessage.textContent = message;
  uploadMessage.classList.toggle("error", isError);
}

function selectFile(file) {
  setUploadMessage("");
  fileToUpload = null;
  uploadButton.disabled = true;
  selectedFile.hidden = true;

  if (!file) return;
  if (!/\.(pdf|txt)$/i.test(file.name)) {
    setUploadMessage("Please choose a PDF or TXT file.", true);
    return;
  }
  if (file.size === 0 || file.size > 10 * 1024 * 1024) {
    setUploadMessage("Choose a non-empty file no larger than 10 MB.", true);
    return;
  }

  fileToUpload = file;
  selectedFile.hidden = false;
  selectedFile.textContent = `${file.name} · ${(file.size / 1024).toFixed(0)} KB`;
  uploadButton.disabled = false;
}

async function readResponse(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
  }
  return body;
}

function resetWorkspace() {
  fileToUpload = null;
  indexedCount = 0;
  sessionDocuments = [];
  documentCount.textContent = "0";
  documentList.replaceChildren(emptyListTemplate.cloneNode(true));
  documentScope.length = 1;
  documentScope.value = "";
  chatHistory.replaceChildren(welcomeTemplate.cloneNode(true));
  questionInput.value = "";
  fileInput.value = "";
  selectedFile.hidden = true;
  uploadButton.disabled = true;
  uploadButton.textContent = "Index document ↗";
  askButton.disabled = false;
  askButton.textContent = "Ask ↗";
  setUploadMessage("");
}

function signOut() {
  if (activeUser) {
    try {
      sessionStorage.removeItem(`indexedDocuments:${activeUser.id}`);
    } catch {
      // Browsers can disable session storage.
    }
  }
  try {
    sessionStorage.removeItem("accessToken");
  } catch {
    // The in-memory token is still cleared below.
  }
  accessToken = null;
  activeUser = null;
  resetWorkspace();
  workspace.hidden = true;
  account.hidden = true;
  authPanel.hidden = false;
}

function signIn(token, user) {
  accessToken = token;
  activeUser = user;
  try {
    sessionStorage.setItem("accessToken", token);
  } catch {
    // Login still works until this page is refreshed.
  }
  resetWorkspace();
  try {
    const saved = JSON.parse(sessionStorage.getItem(`indexedDocuments:${user.id}`) || "[]");
    if (Array.isArray(saved)) {
      sessionDocuments = saved.filter((item) => item.document_id && item.source);
      sessionDocuments.forEach(addIndexedDocument);
    }
  } catch {
    // A blocked or invalid session store should not stop the interface.
  }
  accountName.textContent = user.username;
  authPanel.hidden = true;
  account.hidden = false;
  workspace.hidden = false;
  passwordInput.value = "";
}

async function authorizedFetch(url, options = {}) {
  if (!accessToken) throw new Error("Please log in first.");
  const requestToken = accessToken;
  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${requestToken}`);
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401 && accessToken === requestToken) signOut();
  return response;
}

function showAuthMode(isSignup) {
  signupMode = isSignup;
  authTitle.textContent = isSignup ? "Create your account." : "Welcome back.";
  authSubmit.textContent = isSignup ? "Create account" : "Log in";
  authToggle.textContent = isSignup ? "Already have an account? Log in" : "New here? Create an account";
  passwordInput.autocomplete = isSignup ? "new-password" : "current-password";
  authMessage.textContent = "";
}

function addIndexedDocument(result) {
  if (indexedCount === 0) documentList.replaceChildren();
  indexedCount += 1;
  documentCount.textContent = String(indexedCount);

  const item = document.createElement("div");
  item.className = "document-item";
  const icon = document.createElement("span");
  icon.className = "document-icon";
  icon.textContent = result.source.toLowerCase().endsWith(".pdf") ? "PDF" : "TXT";
  const details = document.createElement("div");
  details.className = "document-details";
  const name = document.createElement("strong");
  name.textContent = result.source;
  const count = document.createElement("small");
  count.textContent = `${result.chunk_count} ${result.chunk_count === 1 ? "chunk" : "chunks"} indexed`;
  details.append(name, count);
  item.append(icon, details);
  documentList.prepend(item);

  const option = document.createElement("option");
  option.value = result.document_id;
  option.textContent = result.source;
  documentScope.append(option);
  documentScope.value = result.document_id;
}

function addMessage(kind, text) {
  document.querySelector("#welcome")?.remove();
  const message = document.createElement("div");
  message.className = `message ${kind}`;
  const label = document.createElement("p");
  label.className = "message-label";
  label.textContent = kind === "user" ? "YOU" : "ANSWER";
  const content = document.createElement("p");
  content.className = "message-text";
  content.textContent = text;
  message.append(label, content);
  chatHistory.append(message);
  chatHistory.scrollTop = chatHistory.scrollHeight;
  return message;
}

function addSources(message, sources) {
  if (!sources?.length) return;

  const heading = document.createElement("p");
  heading.className = "sources-heading";
  heading.textContent = `SOURCES · ${sources.length}`;
  message.append(heading);

  for (const source of sources) {
    const item = document.createElement("details");
    item.className = "source-item";
    const summary = document.createElement("summary");
    const title = document.createElement("span");
    title.className = "source-title";
    title.textContent = `[${source.source_id}] ${source.source}${source.page ? ` · page ${source.page}` : ""}`;
    const arrow = document.createElement("span");
    arrow.textContent = "+";
    summary.append(title, arrow);
    const excerpt = document.createElement("p");
    excerpt.className = "source-text";
    excerpt.textContent = source.text;
    item.append(summary, excerpt);
    message.append(item);
  }
}

fileInput.addEventListener("change", () => selectFile(fileInput.files[0]));

for (const eventName of ["dragenter", "dragover"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
}
dropZone.addEventListener("drop", (event) => selectFile(event.dataTransfer.files[0]));

uploadButton.addEventListener("click", async () => {
  if (!fileToUpload) return;
  const requestUserId = activeUser?.id;
  const requestToken = accessToken;
  uploadButton.disabled = true;
  uploadButton.textContent = "Indexing…";
  setUploadMessage("Extracting text and creating embeddings. This may take a moment.");

  try {
    const form = new FormData();
    form.append("file", fileToUpload);
    const result = await readResponse(await authorizedFetch("/api/v1/ingest", { method: "POST", body: form }));
    if (activeUser?.id !== requestUserId || accessToken !== requestToken) return;
    addIndexedDocument(result);
    sessionDocuments.push(result);
    try {
      sessionStorage.setItem(`indexedDocuments:${activeUser.id}`, JSON.stringify(sessionDocuments));
    } catch {
      // Upload still succeeded if the browser blocks session storage.
    }
    setUploadMessage(`${result.source} is ready for questions.`);
    fileToUpload = null;
    fileInput.value = "";
    selectedFile.hidden = true;
  } catch (error) {
    if (activeUser?.id === requestUserId && accessToken === requestToken) setUploadMessage(error.message, true);
  } finally {
    if (activeUser?.id === requestUserId && accessToken === requestToken) {
      uploadButton.textContent = "Index document ↗";
      uploadButton.disabled = !fileToUpload;
    }
  }
});

authToggle.addEventListener("click", () => showAuthMode(!signupMode));
logoutButton.addEventListener("click", () => {
  const request = authorizedFetch("/api/v1/logout", { method: "POST" });
  signOut();
  request.catch(() => {});
});

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authSubmit.disabled = true;
  authMessage.textContent = "";
  authMessage.classList.remove("error");
  try {
    const path = signupMode ? "/api/v1/signup" : "/api/v1/login";
    const result = await readResponse(await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: usernameInput.value, password: passwordInput.value }),
    }));
    signIn(result.access_token, result.user);
  } catch (error) {
    authMessage.textContent = error.message;
    authMessage.classList.add("error");
  } finally {
    authSubmit.disabled = false;
  }
});

try {
  const savedToken = sessionStorage.getItem("accessToken");
  if (savedToken) {
    fetch("/api/v1/me", { headers: { Authorization: `Bearer ${savedToken}` } })
      .then(readResponse)
      .then((user) => {
        if (!activeUser && sessionStorage.getItem("accessToken") === savedToken) signIn(savedToken, user);
      })
      .catch(() => {
        if (!activeUser && sessionStorage.getItem("accessToken") === savedToken) signOut();
      });
  }
} catch {
  // A browser with storage disabled can still log in for this page visit.
}

questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question || askButton.disabled) return;
  const requestUserId = activeUser?.id;
  const requestToken = accessToken;

  addMessage("user", question);
  questionInput.value = "";
  askButton.disabled = true;
  askButton.textContent = "Thinking…";
  const pending = addMessage("assistant", "Searching your documents…");

  try {
    const response = await readResponse(await authorizedFetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        top_k: 5,
        thinking_mode: thinkingMode.checked,
        document_id: documentScope.value || null,
      }),
    }));
    if (activeUser?.id !== requestUserId || accessToken !== requestToken) return;
    pending.querySelector(".message-text").textContent = response.answer;
    if (response.status !== "ANSWERED") pending.classList.add("refusal");
    addSources(pending, response.sources);
  } catch (error) {
    if (activeUser?.id === requestUserId && accessToken === requestToken) {
      pending.classList.add("refusal");
      pending.querySelector(".message-text").textContent = error.message;
    }
  } finally {
    if (activeUser?.id === requestUserId && accessToken === requestToken) {
      askButton.disabled = false;
      askButton.textContent = "Ask ↗";
      questionInput.focus();
      chatHistory.scrollTop = chatHistory.scrollHeight;
    }
  }
});

fetch("/health")
  .then(readResponse)
  .then(() => {
    connectionStatus.classList.add("online");
    connectionStatus.lastElementChild.textContent = "Backend connected";
  })
  .catch(() => {
    connectionStatus.classList.add("offline");
    connectionStatus.lastElementChild.textContent = "Backend unavailable";
  });
