"use strict";
const start = document.querySelector('#start');
const status = document.querySelector('#status');
const save = document.querySelector('#save');
start.addEventListener('click', async () => {
  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({video: true, audio: true,
      preferCurrentTab: true, selfBrowserSurface: 'include', systemAudio: 'exclude'});
    if (!stream.getAudioTracks().length) throw new Error('Нет звука вкладки. Повторите с включённым звуком.');
    const parts = [];
    const type = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm'].find(t => MediaRecorder.isTypeSupported(t));
    const recorder = new MediaRecorder(stream, {mimeType: type});
    recorder.ondataavailable = event => { if(event.data.size) parts.push(event.data); };
    recorder.onstop = () => {
      stream.getTracks().forEach(track => track.stop());
      save.href = URL.createObjectURL(new Blob(parts, {type}));
      save.download = 'piano-review-demo.webm'; save.hidden = false;
      status.textContent = 'Запись завершена. Сохраните и проверьте звук.';
      start.disabled = false;
    };
    recorder.start(1000); start.disabled = true; save.hidden = true;
    const begin = Date.now();
    const timer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - begin) / 1000);
      status.textContent = `Запись: ${elapsed} / 75 с · звук вкладки включён`;
      if(elapsed >= 75 || recorder.state === 'inactive') {
        clearInterval(timer); if(recorder.state !== 'inactive') recorder.stop();
      }
    }, 1000);
  } catch (error) {
    stream?.getTracks().forEach(track => track.stop());
    status.textContent = `${error.name}: ${error.message}`;
  }
});
