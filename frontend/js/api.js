/** 统一鉴权请求 */
export function createApi(getToken, onUnauthorized) {
  function authHeaders() {
    return {
      Authorization: "Bearer " + getToken(),
      "Content-Type": "application/json",
    };
  }
  async function loadJson(url, options = {}) {
    const r = await fetch(url, {
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
    });
    const j = await r.json().catch(() => ({}));
    if (r.status === 401) {
      onUnauthorized();
      return null;
    }
    return { ok: r.ok, status: r.status, body: j };
  }
  return {
    authHeaders,
    loadJson,
    async get(url) {
      return loadJson(url);
    },
    async post(url, body) {
      return loadJson(url, { method: "POST", body: JSON.stringify(body || {}) });
    },
  };
}
