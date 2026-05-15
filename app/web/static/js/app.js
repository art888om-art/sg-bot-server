"use strict";

// Read a cookie by name. Used to inject the CSRF token into header.
function getCookie(name) {
  const match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : "";
}

window.toast = function (message, type) {
  const host = document.getElementById("toast-host");
  if (!host) return;
  const el = document.createElement("div");
  el.className = "toast " + (type === "error" ? "error" : "success");
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => el.remove(), 4000);
};

window.logout = async function () {
  try {
    await fetch("/api/v1/auth/logout", { method: "POST", headers: csrfHeader() });
  } catch (_e) {
    // ignore
  }
  window.location.href = "/";
};

function csrfHeader() {
  const token = getCookie("csrf_token");
  return token ? { "X-CSRF-Token": token } : {};
}

window.apiFetch = async function (url, options) {
  options = options || {};
  const isWriting = options.method && !["GET", "HEAD"].includes(options.method.toUpperCase());
  options.headers = Object.assign(
    { "Content-Type": "application/json" },
    options.headers || {},
    isWriting ? csrfHeader() : {}
  );
  const res = await fetch(url, options);
  if (res.status === 401) {
    window.location.href = "/login";
    return Promise.reject(new Error("Unauthorized"));
  }
  return res;
};
