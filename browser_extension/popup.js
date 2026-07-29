const apiBase = "http://127.0.0.1:8000";

function setStatus(message) {
  document.getElementById("status").textContent = message || "";
}

function value(id) {
  return document.getElementById(id).value.trim();
}

function setValue(id, text) {
  document.getElementById(id).value = text || "";
}

async function currentTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

function extractPageJob() {
  const ignored = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "SVG"]);
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
  const lines = [];
  let node;
  while ((node = walker.nextNode())) {
    const parent = node.parentElement;
    if (!parent || ignored.has(parent.tagName)) {
      continue;
    }
    const text = node.textContent.replace(/\s+/g, " ").trim();
    if (text && !lines.includes(text)) {
      lines.push(text);
    }
    if (lines.join("\n").length > 18000) {
      break;
    }
  }
  const heading = document.querySelector("h1")?.innerText?.trim() || "";
  return {
    title: heading || document.title || "",
    url: location.href,
    text: lines.join("\n")
  };
}

async function capturePage() {
  try {
    setStatus("正在读取当前页...");
    const tab = await currentTab();
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractPageJob
    });
    const data = result?.result || {};
    if (!value("title")) {
      setValue("title", data.title || "");
    }
    setValue("url", data.url || tab.url || "");
    setValue("jd", data.text || "");
    setStatus("当前页内容已读取，可以补充字段后导入。");
  } catch (error) {
    setStatus(`读取失败：${error.message || error}`);
  }
}

async function importJob() {
  try {
    setStatus("正在导入...");
    const response = await fetch(`${apiBase}/jobs/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: value("title"),
        company: value("company"),
        location: value("location"),
        salary: value("salary"),
        url: value("url"),
        jd_text: value("jd"),
        fetch_url: false
      })
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || response.statusText);
    }
    const job = data.job || {};
    setStatus(`已导入：${job.company || ""} ${job.title || ""}`.trim());
  } catch (error) {
    setStatus(`导入失败：${error.message || error}`);
  }
}

async function bookmarkJob() {
  try {
    setStatus("正在收藏...");
    const response = await fetch(`${apiBase}/jobs/bookmark`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: value("title"),
        company: value("company"),
        platform: "",
        job_id: "",
        note: value("url")
      })
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || response.statusText);
    }
    setStatus("已收藏到 CareerPilot。");
  } catch (error) {
    setStatus(`收藏失败：${error.message || error}`);
  }
}

document.getElementById("capture").addEventListener("click", capturePage);
document.getElementById("bookmark").addEventListener("click", bookmarkJob);
document.getElementById("import").addEventListener("click", importJob);
capturePage();
