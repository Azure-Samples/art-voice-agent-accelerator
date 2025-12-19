export const smoothValue = (prev, target, deltaMs, attackMs, releaseMs) => {
  const timeConstant = target > prev ? attackMs : releaseMs;
  const mix = 1 - Math.exp(-Math.max(deltaMs, 0) / Math.max(timeConstant, 1));
  return prev + (target - prev) * mix;
};
