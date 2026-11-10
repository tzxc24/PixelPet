const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {window: {}};
for (const file of ['lip-sync', 'pet-behavior']) {
  vm.runInNewContext(fs.readFileSync(`frontend/js/${file}.js`, 'utf8'), context);
}

const rate = 8000;
const wav = Buffer.alloc(44 + rate * 2);
wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8);
wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
wav.writeUInt32LE(rate, 24); wav.writeUInt32LE(rate * 2, 28); wav.writeUInt16LE(2, 32);
wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(rate * 2, 40);
for (let index = 0; index < rate; index++) {
  const amplitude = index < 2400 ? 0 : index < 4800 ? 1000 : 15000;
  wav.writeInt16LE(index % 2 ? amplitude : -amplitude, 44 + 2 * index);
}
const lip = context.window.PixelPetLipSync.fromWav(wav.buffer.slice(wav.byteOffset, wav.byteOffset + wav.length));
assert.equal(lip.sample(.1).mouth, 'closed');
assert.equal(lip.sample(.4).mouth, 'small');
assert.equal(lip.sample(.8).mouth, 'large');
assert.equal(lip.sample(2).mouth, 'closed');
assert.equal(context.window.PixelPetLipSync.fromWav(new ArrayBuffer(8)), null);

const Behavior = context.window.PixelPetBehavior;
for (const [roll, kind] of [[0, 'blink'], [.35, 'lookLeft'], [.55, 'lookRight'], [.75, 'sway'], [.95, 'yawn']]) {
  const behavior = new Behavior({now: 0, random: () => roll});
  assert.equal(behavior.update(14000, {idle: true}).kind, kind);
  assert.equal(behavior.update(14001, {idle: false, sleep: true}).kind, 'none');
  assert.equal(behavior.update(14001, {idle: true, sleep: true}).kind, 'sleep');
  assert.equal(behavior.update(180000, {idle: true}).lowActivity, true);
  assert.equal(behavior.touch(180000), 'HAPPY');
  behavior.touch(180300);
  assert.equal(behavior.touch(180700), 'SHY');
  assert.equal(behavior.update(180701, {idle: true, sleep: true}).kind, 'none', 'touch temporarily wakes quiet-hours pet');
}
console.log('PCM RMS mouth levels, autonomous poses, idle, sleep and touch transitions passed');
