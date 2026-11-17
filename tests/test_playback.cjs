// Exercise the actual playback synchronizer with media/DOM boundary adapters.
// Browser checks separately cover native range events and rendered note rows.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
const synchronizer = source.slice(source.indexOf('function updatePlayback('), source.indexOf('function updatePlayButton('));

function sync({ position, selected = 1, paused = true, followSeek = false, pinUntil = null }) {
  const labels = {};
  const range = {};
  const state = { measure: selected, pinUntil, report: { duration: 8.1, comparisons: [
    { measure: 1, start: .1, end: 4.1 }, { measure: 2, start: 4.1, end: 8.1 }
  ] } };
  vm.runInNewContext(synchronizer + '\nupdatePlayback(followSeek);', {
    state, followSeek, media: () => ({ currentTime: position, duration: 8.2, paused }),
    setText: (id, value) => { labels[id] = value; }, time: String,
    $: () => range, selectMeasure: number => { state.measure = number; }
  });
  return { state, labels };
}

assert.equal(sync({ position: 5, followSeek: true }).state.measure, 2, 'Paused scrubbing follows the timeline');
assert.equal(sync({ position: 5 }).state.measure, 1, 'Ordinary paused inspection keeps the selected measure');
assert.equal(sync({ position: 8.2, followSeek: true }).labels['playback-measure'], 'ТАКТ 2', 'Trailing audio keeps the final measure');
assert.equal(sync({ position: 0, selected: 2 }).labels['playback-measure'], 'ТАКТ 1', 'Leading silence labels the first playback measure');
assert.equal(sync({ position: 3.9, selected: 2, paused: false, pinUntil: 4.3 }).state.measure, 2, 'Finding lead-in preserves its target measure');
assert.equal(sync({ position: 5, paused: false, pinUntil: 4.3 }).state.measure, 2, 'Playback follows after the lead-in');
console.log('6 playback synchronization checks passed');
