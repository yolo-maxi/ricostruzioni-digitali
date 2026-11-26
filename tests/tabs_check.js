// Runs the inline script of the viewer against a small stand-in for the DOM.
// No browser is used. Usage: node tests/tabs_check.js public/index.html
// Exit code 0 = every check passed. The script prints one line for each check.
'use strict';
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync(process.argv[2], 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const studyStart = html.indexOf('id="study"');
const fontsStart = html.indexOf('id="fonts"');
const experimentsStart = html.indexOf('id="experiments"');
if (fontsStart < 0 || studyStart < fontsStart) { throw new Error('the two panels were not found in order'); }

// Every element with an id, and the panel that holds it (by position in the file).
const elements = {};
const calls = [];
function makeElement(id, attrs, panelId) {
  const listeners = {};
  const el = {
    id, attrs, hidden: Object.prototype.hasOwnProperty.call(attrs, 'hidden'), tabIndex: Number(attrs.tabindex || 0),
    value: attrs.value || '', textContent: '',
    style: {}, clientWidth: 300, clientHeight: 218,
    get scrollWidth() { return Math.min(300, this.textContent.length * parseFloat(this.style.fontSize || 18) * 0.7); },
    get scrollHeight() { return Math.ceil(this.textContent.length * parseFloat(this.style.fontSize || 18) * 0.7 / 300) * parseFloat(this.style.fontSize || 18) * 1.2; },
    getBoundingClientRect() { return {height: this.scrollHeight}; },
    getAttribute: (n) => (n in el.attrs ? el.attrs[n] : null),
    setAttribute: (n, v) => { el.attrs[n] = String(v); },
    addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
    clearListeners: () => { Object.keys(listeners).forEach((k) => delete listeners[k]); },
    dispatch: (type, event) => (listeners[type] || []).forEach((fn) => fn(Object.assign({preventDefault() { el.prevented = true; }}, event || {}))),
    focus: () => { calls.push('focus:' + id); document.activeElement = el; },
    scrollIntoView: () => { calls.push('scroll:' + id); },
    closest: (selector) => {
      if (selector !== '[role=tabpanel]') { throw new Error('unexpected selector ' + selector); }
      if (el.attrs.role === 'tabpanel') { return el; }
      return panelId ? elements[panelId] : null;
    },
  };
  return el;
}
const tagRe = /<([a-z0-9]+)((?:\s+[a-zA-Z-]+(?:="[^"]*")?)*)\s*>/g;
let m;
while ((m = tagRe.exec(html))) {
  const attrs = {};
  const attrRe = /([a-zA-Z-]+)(?:="([^"]*)")?/g;
  let a;
  while ((a = attrRe.exec(m[2]))) { attrs[a[1]] = a[2] === undefined ? '' : a[2]; }
  if (!attrs.id) { continue; }
  const panelId = m.index > experimentsStart ? 'experiments' : (m.index > studyStart ? 'study' : (m.index > fontsStart ? 'fonts' : null));
  elements[attrs.id] = makeElement(attrs.id, attrs, attrs.role === 'tabpanel' ? null : panelId);
  if (attrs.id.startsWith('live-')) {
    elements[attrs.id].textContent = html.slice(tagRe.lastIndex).split('</span>')[0];
    elements[attrs.id].initialText = elements[attrs.id].textContent;
  }
}
const tabs = Object.values(elements).filter((e) => e.attrs.role === 'tab');
const windowListeners = {};
const location = {hash: ''};
const history = {replaceState: (state, title, url) => { location.hash = url; calls.push('replace:' + url); }};
const document = {
  activeElement: null,
  querySelectorAll: (selector) => {
    if (selector === '.source-page') { return Object.values(elements).filter((e) => e.attrs.class === 'source-page'); }
    if (selector !== '[role=tab]') { throw new Error('unexpected selector ' + selector); }
    return tabs;
  },
  getElementById: (id) => elements[id] || null,
};
const window = {
  addEventListener: (type, fn) => { (windowListeners[type] = windowListeners[type] || []).push(fn); },
  scrollTo: (x, y) => { calls.push('scrollTo:' + x + ',' + y); },
};
function load(hash) {
  Object.values(elements).forEach((e) => {
    e.clearListeners();
    if (e.initialText !== undefined) { e.textContent = e.initialText; }
    if (e.id.startsWith('tester-')) { e.value = ''; }
    if (e.attrs.role === 'tabpanel') { e.hidden = e.id !== 'fonts'; }
    if (e.attrs.role === 'tab') { e.attrs['aria-selected'] = e.id === 'tab-fonts' ? 'true' : 'false'; e.tabIndex = e.id === 'tab-fonts' ? 0 : -1; }
  });
  Object.keys(windowListeners).forEach((k) => delete windowListeners[k]);
  calls.length = 0;
  location.hash = hash;
  vm.runInNewContext(script, {document, window, location, history, decodeURIComponent, Array});
}
function state() {
  const selected = tabs.filter((t) => t.attrs['aria-selected'] === 'true').map((t) => t.id);
  const visible = Object.values(elements).filter((e) => e.attrs.role === 'tabpanel' && !e.hidden).map((e) => e.id);
  const focusable = tabs.filter((t) => t.tabIndex === 0).map((t) => t.id);
  return selected.join() + '|' + visible.join() + '|' + focusable.join();
}
let failed = 0;
function check(name, got, want) {
  const ok = got === want;
  if (!ok) { failed += 1; }
  console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok ? '' : '  got ' + JSON.stringify(got) + '  want ' + JSON.stringify(want)));
}
const FONTS = 'tab-fonts|fonts|tab-fonts';
const STUDY = 'tab-study|study|tab-study';
const EXPERIMENTS = 'tab-experiments|experiments|tab-experiments';

check('three tabs', tabs.map((t) => t.id).join(), 'tab-fonts,tab-study,tab-experiments');
load('');
check('no hash: Fonts is the default tab', state(), FONTS);
check('no hash: the address is not changed', calls.filter((c) => c.startsWith('replace')).length, 0);

elements['tab-study'].dispatch('click');
check('click on Study shows Study', state(), STUDY);
check('click on Study sets the share address', location.hash, '#study');
elements['tab-fonts'].dispatch('click');
check('click on Fonts shows Fonts', state(), FONTS);
check('click on Fonts sets the address', location.hash, '#fonts');

elements['tab-fonts'].dispatch('keydown', {key: 'ArrowRight'});
check('ArrowRight moves to Study', state(), STUDY);
check('ArrowRight moves the focus', document.activeElement.id, 'tab-study');
check('ArrowRight is handled', elements['tab-fonts'].prevented, true);
elements['tab-study'].dispatch('keydown', {key: 'ArrowRight'});
check('ArrowRight moves to Experiments', state(), EXPERIMENTS);
elements['tab-experiments'].dispatch('keydown', {key: 'ArrowRight'});
check('ArrowRight wraps to Fonts', state(), FONTS);
elements['tab-fonts'].dispatch('keydown', {key: 'ArrowLeft'});
check('ArrowLeft wraps to Experiments', state(), EXPERIMENTS);
elements['tab-study'].dispatch('keydown', {key: 'Home'});
check('Home goes to Fonts', state(), FONTS);
elements['tab-fonts'].dispatch('keydown', {key: 'End'});
check('End goes to Experiments', state(), EXPERIMENTS);
const before = state();
elements['tab-study'].dispatch('keydown', {key: 'a'});
check('other keys do nothing', state(), before);

load('#study');
check('address #study opens Study', state(), STUDY);
check('address #study goes to the top of the tab', calls.includes('scrollTo:0,0'), true);
for (const id of ['experiments', 'experiment-blackletter', 'experiment-alphabet', 'experiment-cursive']) {
  load('#' + id);
  check('address #' + id + ' opens Experiments', state(), EXPERIMENTS);
}
elements['tab-experiments'].dispatch('click');
check('click on Experiments sets share address', location.hash, '#experiments');
location.hash = '#fonts';
(windowListeners.hashchange || []).forEach((fn) => fn());
check('hash navigation returns to Fonts', state(), FONTS);
load('#study-stz');
check('address #study-stz opens Study', state(), STUDY);
check('address #study-stz scrolls to the proofs', calls.includes('scroll:study-stz'), true);
for (const id of ['study-capitals', 'study-panel']) {
  load('#' + id);
  check('address #' + id + ' opens Study', state(), STUDY);
  check('address #' + id + ' scrolls to evidence', calls.includes('scroll:' + id), true);
}
load('#face-capitals');
check('address #face-capitals stays on Fonts', state(), FONTS);
check('address #face-capitals scrolls to the card', calls.includes('scroll:face-capitals'), true);
load('#fonts');
check('address #fonts opens Fonts', state(), FONTS);
load('#no-such-place');
check('unknown address keeps the default', state(), FONTS);

load('');
location.hash = '#study-panel';
(windowListeners.hashchange || []).forEach((fn) => fn());
check('a link to #study-panel inside the page opens Study', state(), STUDY);
check('a link to #study-panel scrolls to that section', calls.includes('scroll:study-panel'), true);

for (const k of ['a', 'p']) {
  const text = elements['live-' + k], button = elements['recycle-' + k];
  const input = elements['tester-' + k];
  for (const custom of ['Perché il caffè è già finito?', '日本語 hello <b>test</b>', 'lunghissimo'.repeat(2000), '']) {
    input.value = custom;
    input.dispatch('input');
    check('custom text is rendered literally ' + k + ' length ' + custom.length, text.textContent, custom);
    check('custom text fits mocked bounds ' + k + ' length ' + custom.length, text.scrollHeight <= 218 && text.scrollWidth <= 300, true);
  }
  button.dispatch('click');
  check('recycle clears custom input ' + k, input.value, '');
  check('recycle restores a preset ' + k, text.textContent.length > 30, true);
  load('');
  const seen = new Set();
  const sequence = [];
  for (let i = 0; i < 40; i++) {
    const previous = text.textContent;
    button.dispatch('click');
    if (text.textContent === previous) { throw new Error('immediate sample repetition'); }
    if (text.scrollHeight > 218 || text.scrollWidth > 300) { throw new Error('fit exceeds mocked bounds'); }
    seen.add(text.textContent);
    sequence.push(text.textContent);
  }
  check('recycle visits all five Italian samples ' + k, seen.size, 5);
  check('sample pool varies sentence lengths ' + k, new Set([...seen].map(s => s.length)).size > 3, true);
  load('');
  const replay = [];
  for (let i = 0; i < 40; i++) { button.dispatch('click'); replay.push(text.textContent); }
  check('seeded sequence is reproducible ' + k, JSON.stringify(replay), JSON.stringify(sequence));
  elements['fit-' + k].clientHeight = 100;
  (windowListeners.resize || []).forEach(fn => fn());
  check('resize refits sample height ' + k, text.scrollHeight <= 100, true);
  elements['fit-' + k].clientHeight = 218;
}

console.log(failed ? failed + ' check(s) failed' : 'all checks passed');
process.exit(failed ? 1 : 0);