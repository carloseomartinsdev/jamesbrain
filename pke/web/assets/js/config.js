const cfg = window.__PKE_CONFIG__ || {};

export const API_BASE_URL = (
  cfg.apiBaseUrl && !cfg.apiBaseUrl.includes("__PKE_API_BASE_URL__")
    ? cfg.apiBaseUrl
    : "/api/v1"
);

export const DEBUG_UI = cfg.debugUi === true;
