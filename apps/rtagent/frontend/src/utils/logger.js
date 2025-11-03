// src/utils/logger.js

const LEVEL_PRIORITY = {
  error: 0,
  warn: 1,
  info: 2,
  debug: 3,
};

const globalConsole = globalThis.console || console;

const originalConsole = {
  debug: globalConsole.debug ? globalConsole.debug.bind(globalConsole) : () => {},
  log: globalConsole.log ? globalConsole.log.bind(globalConsole) : () => {},
  info: globalConsole.info ? globalConsole.info.bind(globalConsole) : () => {},
  warn: globalConsole.warn ? globalConsole.warn.bind(globalConsole) : () => {},
  error: globalConsole.error ? globalConsole.error.bind(globalConsole) : () => {},
};

const resolveLevelName = (level) => {
  if (!level) return undefined;
  const normalized = String(level).trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(LEVEL_PRIORITY, normalized)
    ? normalized
    : undefined;
};

let activeLevel = resolveLevelName(import.meta.env?.VITE_APP_LOG_LEVEL)
  || resolveLevelName(import.meta.env?.VITE_LOG_LEVEL)
  || (process.env.NODE_ENV === "production" ? "warn" : "info");

const shouldLog = (level) => {
  if (level === "error") {
    return true;
  }
  const resolvedLevel = resolveLevelName(level) || "info";
  return LEVEL_PRIORITY[resolvedLevel] <= LEVEL_PRIORITY[activeLevel] || process.env.NODE_ENV !== "production";
};

const applyConsoleFiltering = () => {
  globalConsole.debug = (...args) => {
    if (shouldLog("debug")) {
      originalConsole.debug(...args);
    }
  };
  globalConsole.log = (...args) => {
    if (shouldLog("info")) {
      originalConsole.log(...args);
    }
  };
  globalConsole.info = (...args) => {
    if (shouldLog("info")) {
      originalConsole.info(...args);
    }
  };
  globalConsole.warn = (...args) => {
    if (shouldLog("warn")) {
      originalConsole.warn(...args);
    }
  };
  globalConsole.error = (...args) => {
    originalConsole.error(...args);
  };
};

const configureLogLevel = (level) => {
  const resolved = resolveLevelName(level);
  if (resolved) {
    activeLevel = resolved;
    applyConsoleFiltering();
  }
};

applyConsoleFiltering();

const logger = {
  debug: (...args) => globalConsole.debug(...args),
  info: (...args) => globalConsole.info(...args),
  log: (...args) => globalConsole.log(...args),
  warn: (...args) => globalConsole.warn(...args),
  error: (...args) => globalConsole.error(...args),
};

export { configureLogLevel };
export default logger;
