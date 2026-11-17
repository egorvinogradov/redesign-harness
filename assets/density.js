// Keep export density separate from the design's logical CSS dimensions.
export function frameAt(item, step = 0) {
  return {
    standard: step ? item.steps[step - 1] : item.image,
    retina: step ? item.steps2x?.[step - 1] : item.image2x,
    dimensions: step ? item.stepDimensions?.[step - 1] : item.dimensions,
  };
}

export function applyImageDensity(image, ratio) {
  const retina = ratio > 1 && image.dataset.imageRetina;
  const filename = retina || image.dataset.imageStandard;
  if (!filename) return;
  const source = '/assets/' + filename;
  if (image.getAttribute('src') !== source) image.setAttribute('src', source);
  image.dataset.renderDensity = retina ? '2' : '1';
}

export function watchDisplayDensity(onChange, browser = window) {
  let query, lastRatio;
  const update = () => {
    query?.removeEventListener('change', update);
    const ratio = browser.devicePixelRatio || 1;
    lastRatio = ratio;
    query = browser.matchMedia(`(resolution: ${ratio}dppx)`);
    query.addEventListener('change', update);
    onChange(ratio);
  };
  browser.addEventListener('resize', update);
  browser.addEventListener('pageshow', update);
  browser.addEventListener('focus', update);
  update();
  // Some browser/OS display transitions update DPR without a resolution event.
  // A cheap fallback also covers those transitions while keeping both directions exact.
  const timer = browser.setInterval(() => {
    const ratio = browser.devicePixelRatio || 1;
    if (ratio !== lastRatio) update();
    else onChange(ratio);
  }, 500);
  return () => {
    browser.clearInterval(timer);
    query?.removeEventListener('change', update);
    browser.removeEventListener('resize', update);
    browser.removeEventListener('pageshow', update);
    browser.removeEventListener('focus', update);
  };
}
