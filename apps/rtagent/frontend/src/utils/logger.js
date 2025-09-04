// src/utils/logger.js
const logger = {
  log: (...args) => {
    if (process.env.NODE_ENV !== "production") console.log(...args);
  },
  warn: (...args) => {
    if (process.env.NODE_ENV !== "production") console.warn(...args);
  },
  error: (...args) => {
    if (process.env.NODE_ENV !== "production") console.error(...args);
  },
};

export default logger;
